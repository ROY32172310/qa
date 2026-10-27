"""Playwright orchestration and deterministic issue classification."""

from __future__ import annotations

import contextlib
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .config import Settings, Viewport
from .models import AuditReport, Issue, Severity, derive_status
from .probes import ARM_LAYOUT_SHIFT_JS, COLLECT_JS, READ_TIMING_JS, SMOKE_JS


class AuditRuntimeError(RuntimeError):
    """The browser or target could not be executed."""


def audit(
    target: str,
    *,
    settings: Settings | None = None,
    output_dir: str | Path | None = None,
    smoke: bool = True,
) -> AuditReport:
    """Audit one URL and return an evidence-bearing report."""

    cfg = settings or Settings()
    started = datetime.now(timezone.utc)
    started_perf = time.monotonic()
    out_dir = Path(output_dir) if output_dir is not None else Path.cwd() / "webqa-report"
    out_dir.mkdir(parents=True, exist_ok=True)
    shot_dir = out_dir / "screenshots"
    shot_dir.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise AuditRuntimeError(
            "Playwright is not installed. Run: python -m pip install playwright "
            "&& python -m playwright install chromium"
        ) from exc

    issues: list[Issue] = []
    viewport_results: list[dict[str, Any]] = []
    screenshots: list[str] = []
    smoke_result: dict[str, Any] = {"enabled": smoke, "performed": False}
    runtime: dict[str, Any] = {}

    try:
        with sync_playwright() as playwright:
            browser, channel = _launch_browser(playwright, cfg.browser_channel)
            runtime["browser_channel"] = channel
            try:
                for index, viewport in enumerate(cfg.viewports):
                    result = _audit_viewport(
                        browser,
                        target,
                        cfg,
                        viewport,
                        shot_dir,
                        run_smoke=smoke and index == 0,
                    )
                    viewport_results.append(result["measurements"])
                    issues.extend(result["issues"])
                    screenshots.extend(result["screenshots"])
                    if result.get("smoke", {}).get("performed"):
                        smoke_result = result["smoke"]
            finally:
                browser.close()
    except AuditRuntimeError:
        raise
    except Exception as exc:  # noqa: BLE001 - browser setup failures use exit code 2
        raise AuditRuntimeError(f"browser execution failed: {exc}") from exc

    duration_ms = round((time.monotonic() - started_perf) * 1000)
    return AuditReport(
        target=target,
        status=derive_status(issues, cfg.fail_on_warn),
        issues=issues,
        viewports=viewport_results,
        smoke=smoke_result,
        screenshots=screenshots,
        started_at=started.isoformat(),
        duration_ms=duration_ms,
        settings=cfg.to_dict(),
        runtime=runtime,
    )


def _launch_browser(playwright: Any, requested: str) -> tuple[Any, str]:
    if requested:
        try:
            return playwright.chromium.launch(channel=requested, headless=True), requested
        except Exception as exc:  # noqa: BLE001
            raise AuditRuntimeError(
                f"could not launch browser channel {requested!r}: {exc}"
            ) from exc
    try:
        return playwright.chromium.launch(headless=True), "bundled-chromium"
    except Exception:  # noqa: BLE001 - fall back to a system Chrome installation
        try:
            return playwright.chromium.launch(channel="chrome", headless=True), "chrome"
        except Exception as exc:  # noqa: BLE001
            raise AuditRuntimeError(
                "no Chromium browser is available. Run: python -m playwright install chromium"
            ) from exc


def _audit_viewport(
    browser: Any,
    target: str,
    cfg: Settings,
    viewport: Viewport,
    shot_dir: Path,
    *,
    run_smoke: bool,
) -> dict[str, Any]:
    page_errors: list[str] = []
    console_errors: list[str] = []
    failed_requests: list[str] = []
    responses: list[Any] = []
    screenshots: list[str] = []
    smoke: dict[str, Any] = {
        "enabled": run_smoke,
        "performed": False,
        "viewport": viewport.name,
    }
    context = browser.new_context(
        viewport={"width": viewport.width, "height": viewport.height},
        device_scale_factor=viewport.device_scale_factor,
    )
    page = context.new_page()
    page.set_default_timeout(cfg.timeout_ms)
    page.add_init_script(ARM_LAYOUT_SHIFT_JS)
    page.on("pageerror", lambda exc: page_errors.append(str(exc)[:300]))
    page.on(
        "console",
        lambda message: (
            console_errors.append(str(message.text)[:300]) if message.type == "error" else None
        ),
    )
    page.on(
        "requestfailed",
        lambda request: failed_requests.append(
            f"{request.url} ({request.failure or 'unknown failure'})"
        ),
    )
    page.on("response", lambda response: responses.append(response))

    navigation_status = 0
    measurements: dict[str, Any] = {
        "viewport": viewport.to_dict(),
        "status": "error",
    }
    issues: list[Issue]
    try:
        response = page.goto(target, wait_until="load", timeout=cfg.timeout_ms)
        navigation_status = response.status if response is not None else 0
        page.wait_for_timeout(cfg.settle_ms)
        snapshot = page.evaluate(COLLECT_JS, _probe_config(cfg))
        timing = page.evaluate(READ_TIMING_JS) or {}
        network = _network_summary(responses, failed_requests)
        summary = {
            "viewport": viewport.to_dict(),
            "title": snapshot.get("title", ""),
            "url": snapshot.get("url", target),
            "status": "ok",
            "http_status": navigation_status,
            "console_errors": list(console_errors),
            "page_errors": list(page_errors),
            "network": network,
            "timing": timing,
            "measurements": snapshot,
        }
        screenshot = shot_dir / f"{_safe_name(viewport.name)}.png"
        page.screenshot(path=str(screenshot), full_page=False)
        screenshots.append(str(screenshot))
        summary["screenshot"] = str(screenshot)
        measurements = summary
        issues = _issues_for_viewport(summary, cfg)

        if run_smoke:
            smoke = _run_smoke(page, cfg, page_errors, viewport.name)
            if smoke.get("performed"):
                after_shot = shot_dir / f"{_safe_name(viewport.name)}-after-smoke.png"
                with contextlib.suppress(Exception):
                    page.screenshot(path=str(after_shot), full_page=False)
                    screenshots.append(str(after_shot))
                    smoke["screenshot"] = str(after_shot)
                issues.extend(_issues_for_smoke(smoke))
    except Exception as exc:  # noqa: BLE001 - one viewport must not hide the others
        navigation_error = str(exc)[:500]
        measurements = {
            "viewport": viewport.to_dict(),
            "status": "error",
            "http_status": navigation_status,
            "error": navigation_error,
            "console_errors": list(console_errors),
            "page_errors": list(page_errors),
        }
        issues = [
            Issue(
                code="load_error",
                severity="error",
                viewport=viewport.name,
                message=f"page could not be audited: {navigation_error}",
                hint="Check the target URL, authentication, and network availability.",
            )
        ]
    finally:
        context.close()
    return {
        "measurements": measurements,
        "issues": issues,
        "screenshots": screenshots,
        "smoke": smoke,
    }


def _probe_config(cfg: Settings) -> dict[str, Any]:
    return {
        "minTap": cfg.min_tap_target_px,
        "minFont": cfg.min_font_px,
        "overlayRatio": cfg.overlay_ratio,
        "aspectTolerance": cfg.aspect_tolerance,
        "ignore": list(cfg.ignore_selectors),
    }


def _network_summary(responses: Sequence[Any], request_failures: Sequence[str]) -> dict[str, Any]:
    total_bytes = 0
    failed: list[str] = list(request_failures)
    for response in responses:
        try:
            status = int(response.status)
        except Exception:  # noqa: BLE001
            status = 0
        if status >= 400 and not _is_ignorable_failure(response.url):
            failed.append(f"HTTP {status} {response.url}")
        try:
            size = int(response.request.sizes().get("responseBodySize") or 0)
            if size > 0:
                total_bytes += size
        except Exception:  # noqa: BLE001
            pass
    return {
        "request_count": len(responses),
        "transfer_bytes": total_bytes,
        "failures": failed[:30],
        "failure_count": len(failed),
    }


def _is_ignorable_failure(url: str) -> bool:
    return urlsplit(url).path.lower().endswith("/favicon.ico")


def _issues_for_viewport(summary: dict[str, Any], cfg: Settings) -> list[Issue]:
    data = summary["measurements"]
    name = summary["viewport"]["name"]
    issues: list[Issue] = []

    if summary.get("http_status", 0) >= 400:
        issues.append(
            Issue(
                "http_error",
                "error",
                f"main document returned HTTP {summary['http_status']}",
                name,
            )
        )
    if summary.get("page_errors"):
        issues.append(
            Issue(
                "page_error",
                "error",
                f"page raised JavaScript error(s): {'; '.join(summary['page_errors'][:3])}",
                name,
                "Fix the JavaScript exception before testing visual details.",
                {"errors": summary["page_errors"][:10]},
            )
        )
    if summary.get("console_errors"):
        issues.append(
            Issue(
                "console_error",
                "error",
                f"console.error was emitted: {'; '.join(summary['console_errors'][:3])}",
                name,
                "Remove error logging from production paths and fix the underlying failure.",
                {"errors": summary["console_errors"][:10]},
            )
        )
    network_failures = summary["network"].get("failures") or []
    if network_failures:
        issues.append(
            Issue(
                "resource_failure",
                "error",
                f"{summary['network']['failure_count']} request(s) failed: "
                f"{'; '.join(network_failures[:3])}",
                name,
                "Repair missing, blocked, or failing assets.",
                {"failures": network_failures[:10]},
            )
        )
    overflow = int(data.get("overflowX") or 0)
    if overflow > cfg.overflow_tolerance_px:
        issues.append(
            Issue(
                "horizontal_overflow",
                "error",
                f"page is {overflow}px wider than the viewport",
                name,
                "Use max-width, responsive grids, and wrapping instead of fixed widths.",
                {"overflow_px": overflow},
            )
        )
    if (
        int(data.get("textLength") or 0) < cfg.blank_text_chars
        and int(data.get("elementCount") or 0) < cfg.blank_element_count
    ):
        issues.append(
            Issue(
                "blank_page",
                "error",
                "page contains almost no visible text or content",
                name,
            )
        )
    hard_fonts = [
        row for row in data.get("tinyFonts") or [] if float(row.get("px") or 0) < cfg.hard_font_px
    ]
    if hard_fonts:
        issues.append(
            Issue(
                "unreadable_font",
                "error",
                f"{len(hard_fonts)} text node(s) use font smaller than {cfg.hard_font_px:g}px",
                name,
                "Keep body and control text readable; 10px is a hard failure floor.",
                {"samples": hard_fonts[:5]},
            )
        )
    soft_fonts = [
        row for row in data.get("tinyFonts") or [] if float(row.get("px") or 0) >= cfg.hard_font_px
    ]
    if len(soft_fonts) > cfg.small_issue_report_min:
        issues.append(
            Issue(
                "tiny_fonts",
                "warning",
                f"{len(soft_fonts)} text node(s) use font smaller than {cfg.min_font_px:g}px",
                name,
                "Use at least 12px for secondary text and 14-16px for body text.",
                {"samples": soft_fonts[:5]},
            )
        )
    small_targets = data.get("smallTargets") or []
    if len(small_targets) > cfg.small_issue_report_min:
        issues.append(
            Issue(
                "small_tap_targets",
                "warning",
                f"{len(small_targets)} interactive target(s) are smaller than "
                f"{cfg.min_tap_target_px:g}px",
                name,
                "Keep the visual icon small if needed, but expand the hit area to 44x44px.",
                {"samples": small_targets[:5]},
            )
        )
    for overlay in data.get("hugeOverlays") or []:
        issues.append(
            Issue(
                "huge_overlay",
                "warning",
                f"fixed overlay {overlay.get('label')!r} covers more than "
                f"{cfg.overlay_ratio:.0%} of the viewport",
                name,
                "Check for a class-name collision or a layer that lost its intended size.",
                overlay,
            )
        )
    if data.get("brokenImages"):
        issues.append(
            Issue(
                "broken_image",
                "error",
                f"{len(data['brokenImages'])} visible image(s) failed to decode",
                name,
                "Fix the source path, content type, and fallback for real images.",
                {"images": data["brokenImages"][:10]},
            )
        )
    if data.get("distortedMedia"):
        issues.append(
            Issue(
                "media_distortion",
                "error",
                f"{len(data['distortedMedia'])} media element(s) have a distorted aspect ratio",
                name,
                "Let one dimension be auto or use aspect-ratio instead of forcing both axes.",
                {"media": data["distortedMedia"][:10]},
            )
        )
    timing = summary.get("timing") or {}
    fcp = timing.get("firstContentfulPaintMs")
    if isinstance(fcp, (int, float)) and fcp > cfg.fcp_warn_ms:
        issues.append(
            Issue(
                "slow_first_paint",
                "warning",
                f"first contentful paint took {int(fcp)}ms",
                name,
                "Reduce render-blocking assets and above-the-fold payload.",
                {"first_contentful_paint_ms": fcp},
            )
        )
    shift = timing.get("layoutShift") or {}
    clip = float(shift.get("clip") or 0.0)
    if shift.get("supported") and clip > cfg.cls_error:
        issues.append(
            Issue(
                "layout_shift",
                "error",
                f"unexpected layout shift score is {clip:.3f}",
                name,
                "Reserve image/placeholder dimensions and avoid late above-the-fold insertion.",
                {"cls": clip, "max_shift": shift.get("maxShift"), "shifts": shift.get("shifts")},
            )
        )
    elif shift.get("supported") and clip > cfg.cls_warn:
        issues.append(
            Issue(
                "layout_shift",
                "warning",
                f"unexpected layout shift score is {clip:.3f}",
                name,
                "Reserve image/placeholder dimensions and stabilize late-loading content.",
                {"cls": clip, "max_shift": shift.get("maxShift"), "shifts": shift.get("shifts")},
            )
        )
    network = summary["network"]
    bytes_used = int(network.get("transfer_bytes") or 0)
    requests = int(network.get("request_count") or 0)
    budget_severity: Severity | None = None
    threshold = ""
    if bytes_used > cfg.transfer_error_bytes or requests > cfg.request_error_count:
        budget_severity = "error"
        threshold = f"{cfg.transfer_error_bytes / 1000:.0f}KB/{cfg.request_error_count} requests"
    elif bytes_used > cfg.transfer_warn_bytes or requests > cfg.request_warn_count:
        budget_severity = "warning"
        threshold = f"{cfg.transfer_warn_bytes / 1000:.0f}KB/{cfg.request_warn_count} requests"
    if budget_severity is not None:
        issues.append(
            Issue(
                "transfer_budget",
                budget_severity,
                f"initial load transferred {bytes_used / 1000:.0f}KB in {requests} requests",
                name,
                f"Reduce the above-the-fold payload (budget: {threshold}).",
                {"bytes": bytes_used, "requests": requests},
            )
        )
    return issues


def _run_smoke(
    page: Any,
    cfg: Settings,
    page_errors: list[str],
    viewport_name: str,
) -> dict[str, Any]:
    errors_before = len(page_errors)
    pages_before = len(page.context.pages)
    try:
        result = page.evaluate(
            SMOKE_JS,
            {
                "selector": cfg.smoke_selector,
                "ctaPattern": cfg.cta_pattern,
                "navPattern": cfg.nav_pattern,
                "ignore": list(cfg.ignore_selectors),
                "settleMs": max(cfg.settle_ms, 600),
            },
        )
    except Exception as exc:  # noqa: BLE001 - navigation can tear down the execution context
        result = {
            "found": True,
            "changed": len(page.context.pages) > pages_before,
            "clickError": str(exc)[:300],
            "execution_lost": True,
        }
    result = dict(result or {})
    result.update(
        {
            "performed": True,
            "viewport": viewport_name,
            "new_page_count": max(0, len(page.context.pages) - pages_before),
            "page_error_count": max(0, len(page_errors) - errors_before),
        }
    )
    return result


def _issues_for_smoke(smoke: dict[str, Any]) -> list[Issue]:
    name = str(smoke.get("viewport") or "")
    if not smoke.get("found"):
        return [
            Issue(
                "primary_cta_not_found",
                "warning",
                "no primary call-to-action matched the configured pattern",
                name,
                "Set smoke_selector or adjust cta_pattern if this page has a different "
                "primary action.",
            )
        ]
    issues: list[Issue] = []
    if smoke.get("page_error_count"):
        issues.append(
            Issue(
                "cta_page_error",
                "error",
                f"clicking {smoke.get('label')!r} raised a JavaScript error",
                name,
            )
        )
    if not smoke.get("changed") and not smoke.get("new_page_count"):
        detail = smoke.get("clickError") or "DOM, form fields, dialogs, and URL did not change"
        issues.append(
            Issue(
                "dead_primary_cta",
                "error",
                f"clicking {smoke.get('label')!r} had no observable effect: {detail}",
                name,
                "Check event binding, disabled state, overlays, and the handler's error path.",
                smoke,
            )
        )
    return issues


def _safe_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in name).strip("-")
    return cleaned or "viewport"
