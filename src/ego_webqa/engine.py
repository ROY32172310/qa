"""Playwright orchestration and deterministic issue classification."""

from __future__ import annotations

import contextlib
import re
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .config import MOBILE_USER_AGENT, Settings, Viewport
from .models import AuditReport, Issue, Severity, derive_status
from .probes import (
    ACCESSIBILITY_JS,
    ARM_LAYOUT_SHIFT_JS,
    COLLECT_JS,
    READ_TIMING_JS,
    SMOKE_ASSERTIONS_JS,
    SMOKE_JS,
)


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
    if cfg.storage_state and not Path(cfg.storage_state).is_file():
        raise AuditRuntimeError(f"storage state file does not exist: {cfg.storage_state}")

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
    smoke_runs: list[dict[str, Any]] = []
    smoke_result: dict[str, Any] = {
        "enabled": smoke,
        "performed": False,
        "mode": cfg.smoke_mode if smoke else None,
    }
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
                        artifact_base=out_dir,
                        run_smoke=smoke and _should_run_smoke(cfg, index),
                    )
                    viewport_results.append(result["measurements"])
                    issues.extend(result["issues"])
                    screenshots.extend(result["screenshots"])
                    if result.get("smoke", {}).get("performed"):
                        smoke_runs.append(result["smoke"])
                        if not smoke_result.get("performed"):
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
        smoke_runs=smoke_runs,
        screenshots=screenshots,
        started_at=started.isoformat(),
        duration_ms=duration_ms,
        settings=cfg.to_dict(),
        runtime=runtime,
    )


def _should_run_smoke(cfg: Settings, index: int) -> bool:
    return cfg.smoke_scope == "all" or index == 0


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
    artifact_base: Path,
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
    console_ignores = _compile_patterns(cfg.ignore_console_patterns)
    request_ignores = _compile_patterns(cfg.ignore_request_patterns)
    context_options: dict[str, Any] = {
        "viewport": {"width": viewport.width, "height": viewport.height},
        "device_scale_factor": viewport.device_scale_factor,
        "is_mobile": viewport.mobile,
        "has_touch": viewport.mobile,
    }
    if cfg.extra_http_headers:
        context_options["extra_http_headers"] = dict(cfg.extra_http_headers)
    if cfg.http_username:
        context_options["http_credentials"] = {
            "username": cfg.http_username,
            "password": cfg.http_password,
        }
    if cfg.storage_state:
        context_options["storage_state"] = cfg.storage_state
    user_agent = viewport.user_agent or (MOBILE_USER_AGENT if viewport.mobile else "")
    if user_agent:
        context_options["user_agent"] = user_agent
    context = browser.new_context(**context_options)
    page = context.new_page()
    page.set_default_timeout(cfg.timeout_ms)
    page.add_init_script(ARM_LAYOUT_SHIFT_JS)
    page.on("pageerror", lambda exc: page_errors.append(str(exc)[:300]))
    page.on(
        "console",
        lambda message: (
            console_errors.append(str(message.text)[:300])
            if message.type == "error"
            and not _is_ignorable_console_error(message)
            and not _matches_any(str(message.text), console_ignores)
            else None
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
    readiness: dict[str, Any] = {
        "ready_selector": cfg.ready_selector or None,
        "ready_selector_found": None if not cfg.ready_selector else False,
        "network_idle_requested": cfg.wait_for_network_idle,
        "network_idle_reached": None,
        "network_idle_timed_out": None,
        "fonts_ready": None,
    }
    measurements: dict[str, Any] = {
        "viewport": viewport.to_dict(),
        "status": "error",
    }
    issues: list[Issue]
    stage = "navigation"
    try:
        response = page.goto(target, wait_until="load", timeout=cfg.timeout_ms)
        navigation_status = response.status if response is not None else 0
        stage = "ready_selector"
        if cfg.ready_selector:
            page.wait_for_selector(cfg.ready_selector, state="visible", timeout=cfg.timeout_ms)
            readiness["ready_selector_found"] = True
        stage = "network_idle"
        if cfg.wait_for_network_idle:
            try:
                page.wait_for_load_state("networkidle", timeout=min(cfg.timeout_ms, 3_000))
                readiness["network_idle_reached"] = True
                readiness["network_idle_timed_out"] = False
            except Exception:  # noqa: BLE001 - bounded readiness is advisory
                readiness["network_idle_reached"] = False
                readiness["network_idle_timed_out"] = True
        stage = "probe"
        page.wait_for_timeout(cfg.settle_ms)
        try:
            page.evaluate("() => document.fonts ? document.fonts.ready.then(() => true) : true")
            readiness["fonts_ready"] = True
        except Exception:  # noqa: BLE001 - font readiness is advisory
            readiness["fonts_ready"] = False
        snapshot = page.evaluate(COLLECT_JS, _probe_config(cfg))
        if cfg.profile == "accessibility":
            snapshot["accessibility"] = page.evaluate(ACCESSIBILITY_JS)
        timing = page.evaluate(READ_TIMING_JS) or {}
        network = _network_summary(responses, failed_requests, request_ignores)
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
            "readiness": readiness,
            "measurements": snapshot,
        }
        screenshot = shot_dir / f"{_safe_name(viewport.name)}.png"
        page.screenshot(path=str(screenshot), full_page=False)
        screenshot_ref = _artifact_ref(screenshot, artifact_base)
        screenshots.append(screenshot_ref)
        summary["screenshot"] = screenshot_ref
        measurements = summary
        issues = _issues_for_viewport(summary, cfg)

        if run_smoke and navigation_status < 400:
            smoke = _run_smoke(page, cfg, page_errors, viewport.name)
            if smoke.get("performed"):
                after_shot = shot_dir / f"{_safe_name(viewport.name)}-after-smoke.png"
                with contextlib.suppress(Exception):
                    page.screenshot(path=str(after_shot), full_page=False)
                    after_ref = _artifact_ref(after_shot, artifact_base)
                    screenshots.append(after_ref)
                    smoke["screenshot"] = after_ref
                issues.extend(_issues_for_smoke(smoke))
    except Exception as exc:  # noqa: BLE001 - one viewport must not hide the others
        navigation_error = str(exc)[:500]
        issue_code = "ready_selector_not_found" if stage == "ready_selector" else "load_error"
        hint = (
            "Wait for the SPA to render the configured ready_selector."
            if issue_code == "ready_selector_not_found"
            else "Check the target URL, authentication, and network availability."
        )
        measurements = {
            "viewport": viewport.to_dict(),
            "status": "error",
            "http_status": navigation_status,
            "readiness": readiness,
            "error": navigation_error,
            "console_errors": list(console_errors),
            "page_errors": list(page_errors),
        }
        issues = [
            Issue(
                code=issue_code,
                severity="error",
                viewport=viewport.name,
                message=f"page could not be audited: {navigation_error}",
                hint=hint,
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


def _network_summary(
    responses: Sequence[Any],
    request_failures: Sequence[str],
    request_ignores: tuple[re.Pattern[str], ...] = (),
) -> dict[str, Any]:
    included = [
        response for response in responses if not _matches_any(str(response.url), request_ignores)
    ]
    total_bytes = 0
    failed = [
        failure
        for failure in request_failures
        if not _matches_any(failure.split(" (", 1)[0], request_ignores)
    ]
    for response in included:
        try:
            status = int(response.status)
        except Exception:  # noqa: BLE001
            status = 0
        if status >= 400 and not _is_ignorable_failure(response.url, request_ignores):
            failed.append(f"HTTP {status} {response.url}")
        try:
            size = int(response.request.sizes().get("responseBodySize") or 0)
            if size > 0:
                total_bytes += size
        except Exception:  # noqa: BLE001
            pass
    return {
        "request_count": len(included),
        "ignored_request_count": len(responses) - len(included),
        "transfer_bytes": total_bytes,
        "failures": failed[:30],
        "failure_count": len(failed),
    }


def _is_ignorable_failure(
    url: str,
    request_ignores: tuple[re.Pattern[str], ...] = (),
) -> bool:
    return urlsplit(url).path.lower().endswith("/favicon.ico") or _matches_any(url, request_ignores)


def _is_ignorable_console_error(message: Any) -> bool:
    """Ignore the browser's automatic failed favicon request."""

    text = str(getattr(message, "text", ""))
    if not text.startswith("Failed to load resource: the server responded with a status of "):
        return False
    location = getattr(message, "location", None) or {}
    url = str(location.get("url", "")) if hasattr(location, "get") else ""
    return bool(url) and _is_ignorable_failure(url)


def _compile_patterns(patterns: Sequence[str]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern) for pattern in patterns)


def _matches_any(value: str, patterns: Sequence[re.Pattern[str]]) -> bool:
    return any(pattern.search(value) for pattern in patterns)


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
        return issues
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
    readiness = summary.get("readiness") or {}
    if readiness.get("network_idle_timed_out"):
        issues.append(
            Issue(
                "network_idle_timeout",
                "warning",
                "network did not reach idle before the bounded readiness deadline",
                name,
                "Ignore known polling endpoints or use a ready_selector for continuously "
                "active pages.",
                {"timeout_ms": min(cfg.timeout_ms, 3_000)},
            )
        )
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
    issues.extend(_issues_for_accessibility(data, name))
    return issues


def _issues_for_accessibility(data: dict[str, Any], viewport: str) -> list[Issue]:
    accessibility = data.get("accessibility")
    if not isinstance(accessibility, dict):
        return []
    issues: list[Issue] = []
    if not accessibility.get("lang"):
        issues.append(
            Issue(
                "missing_html_lang",
                "warning",
                "document language is not declared",
                viewport,
                'Set the html lang attribute, for example <html lang="zh-CN">.',
            )
        )
    if not accessibility.get("title"):
        issues.append(
            Issue(
                "missing_page_title",
                "warning",
                "document title is empty",
                viewport,
                "Give every page a unique, descriptive title.",
            )
        )
    missing_names = accessibility.get("missingNames") or []
    if missing_names:
        issues.append(
            Issue(
                "control_missing_name",
                "error",
                f"{len(missing_names)} interactive control(s) have no accessible name",
                viewport,
                "Add visible text, a label, aria-label, or aria-labelledby.",
                {"controls": missing_names[:10]},
            )
        )
    missing_alt = accessibility.get("imagesMissingAlt") or []
    if missing_alt:
        issues.append(
            Issue(
                "image_missing_alt",
                "error",
                f"{len(missing_alt)} visible image(s) have no alt attribute",
                viewport,
                'Describe meaningful images; use alt="" only for decorative images.',
                {"images": missing_alt[:10]},
            )
        )
    duplicate_ids = accessibility.get("duplicateIds") or []
    if duplicate_ids:
        issues.append(
            Issue(
                "duplicate_id",
                "warning",
                f"{len(duplicate_ids)} duplicate HTML id value(s) were found",
                viewport,
                "Use unique ids so labels and ARIA references resolve deterministically.",
                {"ids": duplicate_ids[:10]},
            )
        )
    heading_skips = accessibility.get("headingSkips") or []
    if heading_skips:
        issues.append(
            Issue(
                "heading_level_skip",
                "warning",
                f"{len(heading_skips)} heading level jump(s) were found",
                viewport,
                "Keep heading levels sequential to preserve document navigation.",
                {"jumps": heading_skips[:10]},
            )
        )
    positive_tabindex = accessibility.get("positiveTabindex") or []
    if positive_tabindex:
        issues.append(
            Issue(
                "positive_tabindex",
                "warning",
                f"{len(positive_tabindex)} element(s) use a positive tabindex",
                viewport,
                "Use the natural DOM order and tabindex=0 or -1 only where required.",
                {"elements": positive_tabindex[:10]},
            )
        )
    hidden_focusable = accessibility.get("hiddenFocusable") or []
    if hidden_focusable:
        issues.append(
            Issue(
                "aria_hidden_focusable",
                "error",
                f"{len(hidden_focusable)} focusable element(s) are inside aria-hidden content",
                viewport,
                "Remove the element from the tab order or stop hiding its container.",
                {"elements": hidden_focusable[:10]},
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
    blocked_requests: list[dict[str, str]] = []

    def block_request(route: Any) -> None:
        request = route.request
        blocked_requests.append(
            {
                "method": str(request.method),
                "resource_type": str(request.resource_type),
                "url": str(request.url)[:300],
            }
        )
        route.abort("blockedbyclient")

    safe = cfg.smoke_mode == "safe"
    if safe:
        page.context.route("**/*", block_request)
        page.context.set_offline(True)
    assertion_config = {
        "successSelector": cfg.smoke_success_selector,
        "successUrlPattern": cfg.smoke_success_url_pattern,
    }
    assertions_before: list[dict[str, Any]] = []
    if cfg.smoke_success_selector or cfg.smoke_success_url_pattern:
        with contextlib.suppress(Exception):
            assertions_before = page.evaluate(SMOKE_ASSERTIONS_JS, assertion_config) or []
    url_before = page.url
    try:
        result = page.evaluate(
            SMOKE_JS,
            {
                "selector": cfg.smoke_selector,
                "successSelector": cfg.smoke_success_selector,
                "successUrlPattern": cfg.smoke_success_url_pattern,
                "ctaPattern": cfg.cta_pattern,
                "navPattern": cfg.nav_pattern,
                "ignore": list(cfg.ignore_selectors),
                "settleMs": cfg.smoke_settle_ms,
            },
        )
    except Exception as exc:  # noqa: BLE001 - navigation can tear down the execution context
        with contextlib.suppress(Exception):
            page.wait_for_load_state("domcontentloaded", timeout=min(cfg.timeout_ms, 3_000))
        with contextlib.suppress(Exception):
            page.wait_for_timeout(cfg.smoke_settle_ms)
        assertions_after: list[dict[str, Any]] = []
        with contextlib.suppress(Exception):
            assertions_after = page.evaluate(SMOKE_ASSERTIONS_JS, assertion_config) or []
        assertions = _merge_smoke_assertions(assertions_before, assertions_after)
        result = {
            "found": True,
            "changed": len(page.context.pages) > pages_before or page.url != url_before,
            "clickError": str(exc)[:300],
            "execution_lost": True,
            "assertions": assertions,
            "assertionConfigured": bool(assertions),
            "assertionMatched": bool(assertions)
            and all(assertion["matched"] for assertion in assertions),
        }
    finally:
        if safe:
            page.context.unroute("**/*", block_request)
    result = dict(result or {})
    new_page_errors = page_errors[errors_before:]
    suppressed_network_errors = [
        error
        for error in new_page_errors
        if safe and blocked_requests and _is_blocked_network_error(error)
    ]
    actionable_page_errors = [
        error for error in new_page_errors if error not in suppressed_network_errors
    ]
    new_page_count = max(0, len(page.context.pages) - pages_before)
    assertion_configured = bool(cfg.smoke_success_selector or cfg.smoke_success_url_pattern)
    observed_effect = bool(result.get("changed") or new_page_count or blocked_requests)
    success = bool(result.get("assertionMatched")) if assertion_configured else observed_effect
    result.update(
        {
            "performed": True,
            "mode": cfg.smoke_mode,
            "offline": safe,
            "viewport": viewport_name,
            "new_page_count": new_page_count,
            "observed_effect": observed_effect,
            "assertion_configured": assertion_configured,
            "assertion_required": cfg.smoke_require_assertion,
            "success": success,
            "page_error_count": len(actionable_page_errors),
            "page_errors": actionable_page_errors[:10],
            "suppressed_network_errors": suppressed_network_errors[:10],
            "blocked_request_count": len(blocked_requests),
            "blocked_requests": blocked_requests[:10],
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
    success = smoke.get("success")
    if success is None:
        success = bool(
            smoke.get("changed")
            or smoke.get("new_page_count")
            or smoke.get("blocked_request_count")
        )
    if not success:
        detail = smoke.get("clickError") or "DOM, form fields, dialogs, and URL did not change"
        if smoke.get("assertion_configured"):
            failed_assertions = [
                assertion
                for assertion in smoke.get("assertions") or []
                if not assertion.get("matched")
            ]
            issues.append(
                Issue(
                    "cta_assertion_failed",
                    "error",
                    f"clicking {smoke.get('label')!r} did not satisfy the success assertion",
                    name,
                    "Make the success selector visible, satisfy the URL pattern, or adjust "
                    "the configured post-click assertion.",
                    {"assertions": failed_assertions, "smoke": smoke},
                )
            )
            return issues
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


def _merge_smoke_assertions(
    before: Sequence[dict[str, Any]],
    after: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = []
    for index, current in enumerate(after):
        previous = before[index] if index < len(before) else {}
        matched_before = bool(previous.get("matched"))
        matched_after = bool(current.get("matched"))
        merged.append(
            {
                **current,
                "matchedBefore": matched_before,
                "matchedAfter": matched_after,
                "matched": matched_after and not matched_before,
            }
        )
    return merged


def _is_blocked_network_error(error: str) -> bool:
    lowered = error.lower()
    markers = (
        "failed to fetch",
        "load failed",
        "networkerror",
        "net::err_failed",
        "err_blocked_by_client",
    )
    return any(marker in lowered for marker in markers)


def _artifact_ref(path: Path, output_dir: Path) -> str:
    try:
        return path.relative_to(output_dir).as_posix()
    except ValueError:
        return path.as_posix()


def _safe_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in name).strip("-")
    return cleaned or "viewport"
