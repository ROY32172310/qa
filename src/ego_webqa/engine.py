"""Playwright orchestration and deterministic issue classification."""

from __future__ import annotations

import contextlib
import os
import re
import sys
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit

from .config import (
    MOBILE_USER_AGENT,
    OVERRIDE_SEVERITY_TO_ISSUE,
    SMOKE_ASSERTION_ACTIONS,
    SMOKE_INTERACTION_ACTIONS,
    OverrideResolution,
    Settings,
    Viewport,
    resolve_overrides,
)
from .models import AuditReport, Issue, Severity, derive_status
from .probes import (
    ACCESSIBILITY_JS,
    ARM_LAYOUT_SHIFT_JS,
    COLLECT_JS,
    READ_TIMING_JS,
    SMOKE_ASSERTIONS_JS,
    SMOKE_JS,
    TEXT_SCALE_JS,
)


class AuditRuntimeError(RuntimeError):
    """The browser or target could not be executed."""


def _trace_stage(scope: str, stage: str, started: float) -> None:
    """Emit opt-in execution progress for diagnosing an unbounded wait."""

    if os.environ.get("EGO_WEBQA_TRACE") == "1":
        elapsed_ms = round((time.monotonic() - started) * 1000)
        print(f"[ego-webqa trace] {scope}: {stage} ({elapsed_ms}ms)", file=sys.stderr, flush=True)


def audit(
    target: str,
    *,
    settings: Settings | None = None,
    output_dir: str | Path | None = None,
    smoke: bool = True,
    _retry_transient: bool = True,
    _as_of: date | None = None,
) -> AuditReport:
    """Audit one URL and return an evidence-bearing report."""

    started = datetime.now(timezone.utc)
    resolution = resolve_overrides(settings or Settings(), as_of=_as_of or started.date())
    cfg = resolution.settings
    started_perf = time.monotonic()
    out_dir = Path(output_dir) if output_dir is not None else Path.cwd() / "webqa-report"
    out_dir.mkdir(parents=True, exist_ok=True)
    shot_dir = out_dir / "screenshots"
    shot_dir.mkdir(parents=True, exist_ok=True)
    if cfg.storage_state and not Path(cfg.storage_state).is_file():
        raise AuditRuntimeError(f"storage state file does not exist: {cfg.storage_state}")
    if len(cfg.viewports) > 1:
        return _audit_concurrently(
            target,
            cfg,
            out_dir,
            smoke=smoke,
            started=started,
            started_perf=started_perf,
            retry_transient=_retry_transient,
        )

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
            browser, channel = _launch_browser(
                playwright,
                cfg.browser_engine,
                cfg.browser_channel,
            )
            runtime["browser_engine"] = cfg.browser_engine
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
    issues = _apply_override_audit(issues, resolution)
    report = AuditReport(
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
        governance=resolution.to_dict(),
    )
    transient_reason = _transient_execution_retry_reason(report)
    if _retry_transient and transient_reason:
        retried = audit(
            target,
            settings=cfg,
            output_dir=out_dir,
            smoke=smoke,
            _retry_transient=False,
            _as_of=started.date(),
        )
        _mark_transient_retry(retried, transient_reason)
        retried.duration_ms = round((time.monotonic() - started_perf) * 1000)
        return retried
    return report


def _audit_concurrently(
    target: str,
    cfg: Settings,
    out_dir: Path,
    *,
    smoke: bool,
    started: datetime,
    started_perf: float,
    retry_transient: bool,
) -> AuditReport:
    def run(index: int, viewport: Viewport) -> AuditReport:
        report = audit(
            target,
            settings=replace(cfg, viewports=(viewport,)),
            output_dir=out_dir,
            smoke=smoke and _should_run_smoke(cfg, index),
            _retry_transient=False,
            _as_of=started.date(),
        )
        transient_reason = _transient_execution_retry_reason(report)
        if retry_transient and transient_reason:
            report = audit(
                target,
                settings=replace(cfg, viewports=(viewport,)),
                output_dir=out_dir,
                smoke=smoke and _should_run_smoke(cfg, index),
                _retry_transient=False,
                _as_of=started.date(),
            )
            _mark_transient_retry(report, transient_reason)
        return report

    try:
        with ThreadPoolExecutor(max_workers=min(3, len(cfg.viewports))) as pool:
            futures = [
                pool.submit(run, index, viewport) for index, viewport in enumerate(cfg.viewports)
            ]
            reports = [future.result() for future in futures]
    except AuditRuntimeError:
        raise
    except Exception as exc:  # noqa: BLE001 - parallel browser launch failures use exit code 2
        raise AuditRuntimeError(f"parallel browser execution failed: {exc}") from exc

    issues = [issue for report in reports for issue in report.issues]
    viewport_results = [row for report in reports for row in report.viewports]
    issues = _downgrade_partial_navigation_timeouts(issues, viewport_results)
    screenshots = [shot for report in reports for shot in report.screenshots]
    smoke_runs = [run for report in reports for run in report.smoke_runs]
    performed = next(
        (report.smoke for report in reports if report.smoke.get("performed")),
        {
            "enabled": smoke,
            "performed": False,
            "mode": cfg.smoke_mode if smoke else None,
        },
    )
    channels = sorted(
        {
            str(report.runtime.get("browser_channel"))
            for report in reports
            if report.runtime.get("browser_channel")
        }
    )
    transient_retry_count = sum(
        int(report.runtime.get("transient_retry_count") or 0) for report in reports
    )
    transient_retry_reasons = sorted(
        {
            str(report.runtime.get("transient_retry_reason"))
            for report in reports
            if report.runtime.get("transient_retry_reason")
        }
    )
    runtime: dict[str, Any] = {
        "browser_engine": cfg.browser_engine,
        "browser_channel": ",".join(channels),
    }
    if transient_retry_count:
        runtime["transient_retry_count"] = transient_retry_count
        runtime["transient_retry_reason"] = ",".join(transient_retry_reasons)
    resolution = resolve_overrides(cfg, as_of=started.date())
    issues = _apply_override_audit(issues, resolution)
    return AuditReport(
        target=target,
        status=derive_status(issues, cfg.fail_on_warn),
        issues=issues,
        viewports=viewport_results,
        smoke=performed,
        smoke_runs=smoke_runs,
        screenshots=screenshots,
        started_at=started.isoformat(),
        duration_ms=round((time.monotonic() - started_perf) * 1000),
        settings=cfg.to_dict(),
        runtime=runtime,
        governance=resolution.to_dict(),
    )


def _should_run_smoke(cfg: Settings, index: int) -> bool:
    return cfg.smoke_scope == "all" or index == 0


def _apply_override_audit(
    issues: Sequence[Issue],
    resolution: OverrideResolution,
) -> list[Issue]:
    """Apply effective severities and attach immutable governance evidence."""

    active = {override.dimension_id: override for override in resolution.active}
    governed: list[Issue] = []
    for issue in issues:
        override = active.get(issue.code)
        if override is None:
            governed.append(issue)
            continue
        previous_override = issue.override if issue.severity_source == "override" else {}
        stored_default = previous_override.get("default_severity")
        default_severity = (
            stored_default if stored_default in {"error", "warning"} else issue.severity
        )
        effective_severity = cast(
            Severity,
            (
                OVERRIDE_SEVERITY_TO_ISSUE[override.severity]
                if override.severity
                else default_severity
            ),
        )
        audit = {
            "dimension_id": override.dimension_id,
            "reason": override.reason,
            "owner": override.owner,
            "expires": override.expires,
            "parameters": dict(override.parameters),
            "default_severity": default_severity,
            "effective_severity": effective_severity,
            "severity_changed": effective_severity != default_severity,
            "downgraded": default_severity == "error" and effective_severity == "warning",
        }
        governed.append(
            replace(
                issue,
                severity=effective_severity,
                severity_source="override",
                override=audit,
            )
        )
    return governed


def _launch_browser(playwright: Any, engine: str, requested_channel: str) -> tuple[Any, str]:
    if engine == "firefox":
        try:
            return playwright.firefox.launch(headless=True), "bundled-firefox"
        except Exception as exc:  # noqa: BLE001
            raise AuditRuntimeError(
                "Firefox is not available. Run: python -m playwright install firefox"
            ) from exc
    if engine == "webkit":
        try:
            return playwright.webkit.launch(headless=True), "bundled-webkit"
        except Exception as exc:  # noqa: BLE001
            raise AuditRuntimeError(
                "WebKit is not available. Run: python -m playwright install webkit"
            ) from exc
    if requested_channel:
        try:
            return (
                playwright.chromium.launch(channel=requested_channel, headless=True),
                requested_channel,
            )
        except Exception as exc:  # noqa: BLE001
            raise AuditRuntimeError(
                f"could not launch browser channel {requested_channel!r}: {exc}"
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
    viewport_started = time.monotonic()
    page_errors: list[str] = []
    console_errors: list[str] = []
    failed_requests: list[dict[str, Any]] = []
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
    if cfg.browser_engine == "firefox":
        context_options.pop("is_mobile")
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
    _trace_stage(viewport.name, "context_ready", viewport_started)
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
        lambda request: failed_requests.append(_request_failure_record(request)),
    )
    page.on("response", lambda response: responses.append(response))

    navigation_status = 0
    readiness: dict[str, Any] = {
        "navigation_wait_until": "commit",
        "navigation_attempts": 0,
        "viewport_retry": False,
        "viewport_retry_reason": None,
        "dom_content_loaded": False,
        "dom_content_loaded_timed_out": None,
        "dom_content_loaded_timeout_ms": min(cfg.timeout_ms, 3_000),
        "load_event_reached": None,
        "load_event_timed_out": None,
        "load_event_timeout_ms": min(cfg.timeout_ms, 3_000),
        "ready_selector": cfg.ready_selector or None,
        "ready_selector_found": None if not cfg.ready_selector else False,
        "network_idle_requested": cfg.wait_for_network_idle,
        "network_idle_reached": None,
        "network_idle_timed_out": None,
        "fonts_ready": None,
        "text_scale_applied": None,
    }
    measurements: dict[str, Any] = {
        "viewport": viewport.to_dict(),
        "status": "error",
    }
    issues: list[Issue]
    stage = "navigation"
    try:
        response, navigation_attempts = _goto_document(page, target, cfg.timeout_ms)
        _trace_stage(viewport.name, "navigation_complete", viewport_started)
        readiness["navigation_attempts"] = navigation_attempts
        navigation_status = response.status if response is not None else 0
        stage = "dom_content_loaded"
        readiness["dom_content_loaded"] = _wait_for_dom_content_loaded(
            page,
            readiness["dom_content_loaded_timeout_ms"],
        )
        _trace_stage(viewport.name, "dom_content_loaded_complete", viewport_started)
        readiness["dom_content_loaded_timed_out"] = not readiness["dom_content_loaded"]
        stage = "load_event"
        try:
            page.wait_for_load_state("load", timeout=readiness["load_event_timeout_ms"])
            readiness["load_event_reached"] = True
            readiness["load_event_timed_out"] = False
        except Exception:  # noqa: BLE001 - rendered DOM remains auditable
            readiness["load_event_reached"] = False
            readiness["load_event_timed_out"] = True
        _trace_stage(viewport.name, "load_event_complete", viewport_started)
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
        _trace_stage(viewport.name, "settle_complete", viewport_started)
        if viewport.text_scale > 1:
            _apply_text_scale(page, viewport.text_scale, cfg.timeout_ms)
            readiness["text_scale_applied"] = True
            page.wait_for_timeout(min(cfg.settle_ms, 100))
            _trace_stage(viewport.name, "text_scale_complete", viewport_started)
        try:
            page.evaluate("() => document.fonts ? document.fonts.ready.then(() => true) : true")
            readiness["fonts_ready"] = True
        except Exception:  # noqa: BLE001 - font readiness is advisory
            readiness["fonts_ready"] = False
        _trace_stage(viewport.name, "fonts_complete", viewport_started)
        snapshot = _collect_snapshot(page, cfg, viewport)
        _trace_stage(viewport.name, "collect_complete", viewport_started)
        snapshot["environment"]["textScale"] = viewport.text_scale
        snapshot["environment"]["safeAreaBottomPx"] = viewport.safe_area_bottom_px
        if cfg.profile == "accessibility":
            snapshot["accessibility"] = page.evaluate(ACCESSIBILITY_JS)
        timing = page.evaluate(READ_TIMING_JS) or {}
        _trace_stage(viewport.name, "timing_complete", viewport_started)
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
        _trace_stage(viewport.name, "screenshot_complete", viewport_started)
        screenshot_ref = _artifact_ref(screenshot, artifact_base)
        screenshots.append(screenshot_ref)
        summary["screenshot"] = screenshot_ref
        measurements = summary
        issues = _issues_for_viewport(summary, cfg)
        _trace_stage(viewport.name, "issues_complete", viewport_started)

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
                evidence={
                    "error": navigation_error,
                    "readiness": dict(readiness),
                    "status": "error",
                },
            )
        ]
    finally:
        _trace_stage(viewport.name, "context_close_start", viewport_started)
        context.close()
        _trace_stage(viewport.name, "context_close_complete", viewport_started)
    return {
        "measurements": measurements,
        "issues": issues,
        "screenshots": screenshots,
        "smoke": smoke,
    }


def _goto_document(page: Any, target: str, timeout_ms: int) -> tuple[Any, int]:
    """Navigate once; transient navigation retries use a fresh context."""

    response = page.goto(
        target,
        wait_until="commit",
        timeout=timeout_ms,
    )
    return response, 1


def _has_transient_navigation_timeout(report: AuditReport) -> bool:
    """Return whether a retry with a fresh browser context may recover."""

    return _transient_execution_retry_reason(report) == "navigation_timeout"


def _transient_execution_retry_reason(report: AuditReport) -> str:
    """Name a bounded execution race that a fresh context may recover."""

    for viewport in report.viewports:
        if viewport.get("status") != "error":
            continue
        error = str(viewport.get("error") or "").lower()
        if "page.goto" in error and "timeout" in error:
            return "navigation_timeout"
        if "document root did not become ready for text scaling" in error:
            return "document_replacement"
        if "page dom did not stabilize for measurement" in error:
            return "document_replacement"
    return ""


def _downgrade_partial_navigation_timeouts(
    issues: Sequence[Issue],
    viewports: Sequence[Mapping[str, Any]],
) -> list[Issue]:
    """Treat isolated navigation timeouts as incomplete evidence, not page defects."""

    successful = [
        str(item.get("viewport", {}).get("name") or "")
        for item in viewports
        if item.get("status") == "ok" and item.get("viewport", {}).get("name")
    ]
    if not successful:
        return list(issues)
    timed_out = {
        str(item.get("viewport", {}).get("name") or "")
        for item in viewports
        if item.get("status") == "error"
        and "page.goto" in str(item.get("error") or "").lower()
        and "timeout" in str(item.get("error") or "").lower()
    }
    downgraded: list[Issue] = []
    for issue in issues:
        if issue.code != "load_error" or issue.viewport not in timed_out:
            downgraded.append(issue)
            continue
        downgraded.append(
            replace(
                issue,
                severity="warning",
                hint=(
                    "This viewport timed out after a fresh retry while other viewports "
                    "loaded. Rerun before treating it as a page defect."
                ),
                evidence={
                    **issue.evidence,
                    "partial_navigation_timeout": True,
                    "successful_viewports": len(successful),
                },
            )
        )
    return downgraded


def _mark_transient_retry(report: AuditReport, reason: str) -> None:
    report.runtime["transient_retry_count"] = 1
    report.runtime["transient_retry_reason"] = reason
    for viewport in report.viewports:
        readiness = viewport.get("readiness")
        if isinstance(readiness, dict):
            readiness["viewport_retry"] = True
            readiness["viewport_retry_reason"] = reason


def _apply_text_scale(page: Any, scale: float, timeout_ms: int) -> dict[str, Any]:
    """Apply text scaling after the next document root is available."""

    wait_ms = min(timeout_ms, 3_000)
    last_error: Exception | None = None
    for _ in range(2):
        try:
            page.wait_for_selector("html", state="attached", timeout=wait_ms)
            result = page.evaluate(TEXT_SCALE_JS, scale)
            if isinstance(result, Mapping) and result.get("applied"):
                return dict(result)
        except Exception as exc:  # noqa: BLE001 - retry a navigation race once
            last_error = exc
        page.wait_for_timeout(100)
    message = "document root did not become ready for text scaling"
    if last_error is not None:
        message = f"{message}: {last_error}"
    raise RuntimeError(message) from last_error


def _collect_snapshot(
    page: Any,
    cfg: Settings,
    viewport: Viewport,
    *,
    attempts: int = 3,
) -> dict[str, Any]:
    """Collect measurements after a bounded retry across document replacement."""

    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            snapshot = page.evaluate(COLLECT_JS, _probe_config(cfg, viewport))
        except Exception as exc:  # noqa: BLE001 - a navigation can replace the context
            last_error = exc
        else:
            if isinstance(snapshot, Mapping) and isinstance(snapshot.get("viewport"), Mapping):
                return dict(snapshot)
            last_error = RuntimeError("document root or body was not available")
        if attempt + 1 < attempts:
            page.wait_for_timeout(150)
    raise RuntimeError(f"page DOM did not stabilize for measurement: {last_error}")


def _wait_for_dom_content_loaded(page: Any, timeout_ms: int) -> bool:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        return True
    except Exception:  # noqa: BLE001 - rendered DOM remains auditable
        return False


def _probe_config(cfg: Settings, viewport: Viewport) -> dict[str, Any]:
    return {
        "minTap": cfg.min_tap_target_px,
        "minFont": cfg.min_font_px,
        "overlayRatio": cfg.overlay_ratio,
        "overflowTolerance": cfg.overflow_tolerance_px,
        "aspectTolerance": cfg.aspect_tolerance,
        "aspectMinPx": cfg.aspect_min_rendered_px,
        "safeBottom": viewport.safe_area_bottom_px,
        "ignore": list(cfg.ignore_selectors),
    }


def _network_summary(
    responses: Sequence[Any],
    request_failures: Sequence[str | dict[str, Any]],
    request_ignores: tuple[re.Pattern[str], ...] = (),
) -> dict[str, Any]:
    included = [
        response for response in responses if not _matches_any(str(response.url), request_ignores)
    ]
    total_bytes = 0
    failures: list[dict[str, Any]] = []
    for failure in request_failures:
        record = (
            _normalize_request_failure(failure)
            if isinstance(failure, str)
            else _copy_request_failure(failure)
        )
        if not _is_ignorable_failure(record["url"], request_ignores) and not (
            record["kind"] == "request_failed"
            and _is_ignorable_request_failure(f"{record['url']} ({record['error']})")
        ):
            failures.append(record)
    for response in included:
        try:
            status = int(response.status)
        except Exception:  # noqa: BLE001
            status = 0
        if status >= 400 and not _is_ignorable_failure(response.url, request_ignores):
            failures.append(_response_failure_record(response, status))
        try:
            size = int(response.request.sizes().get("responseBodySize") or 0)
            if size > 0:
                total_bytes += size
        except Exception:  # noqa: BLE001
            pass
    unique_failures = _deduplicate_failures(failures)
    resource_types: dict[str, int] = {}
    kinds: dict[str, int] = {}
    for failure in failures:
        resource_type = str(failure.get("resource_type") or "unknown")
        resource_types[resource_type] = resource_types.get(resource_type, 0) + 1
        kind = str(failure.get("kind") or "unknown")
        kinds[kind] = kinds.get(kind, 0) + 1
    return {
        "request_count": len(included),
        "ignored_request_count": len(responses) - len(included),
        "transfer_bytes": total_bytes,
        "failures": [_failure_label(failure) for failure in unique_failures[:30]],
        "failure_details": unique_failures[:20],
        "failure_count": len(failures),
        "unique_failure_count": len(unique_failures),
        "failure_kind_counts": kinds,
        "failed_resource_type_counts": resource_types,
    }


def _request_failure_record(request: Any) -> dict[str, Any]:
    """Capture stable request attribution without retaining query or credentials."""

    url = _redact_url(str(request.url))
    frame_url = _request_frame_url(request)
    redirected_from = _request_redirected_from(request)
    return {
        "kind": "request_failed",
        "method": str(request.method or "GET").upper(),
        "resource_type": str(request.resource_type or "unknown"),
        "url": url,
        "frame_url": frame_url,
        "redirected_from": redirected_from,
        "same_origin": _same_origin(url, frame_url),
        "is_navigation": _request_is_navigation(request),
        "status": None,
        "error": str(request.failure or "unknown failure"),
    }


def _response_failure_record(response: Any, status: int) -> dict[str, Any]:
    request = response.request
    url = _redact_url(str(response.url))
    frame_url = _request_frame_url(request, response)
    redirected_from = _request_redirected_from(request, response)
    return {
        "kind": "http_error",
        "method": str(getattr(request, "method", "GET") or "GET").upper(),
        "resource_type": str(getattr(request, "resource_type", "unknown") or "unknown"),
        "url": url,
        "frame_url": frame_url,
        "redirected_from": redirected_from,
        "same_origin": _same_origin(url, frame_url),
        "is_navigation": _request_is_navigation(request, response),
        "status": status,
        "error": f"HTTP {status}",
    }


def _request_frame_url(request: Any, response: Any | None = None) -> str:
    candidates = [request, response]
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            frame = candidate.frame
            return _redact_url(str(frame.url))
        except Exception:  # noqa: BLE001 - attribution remains optional
            continue
    return ""


def _request_redirected_from(request: Any, response: Any | None = None) -> str:
    candidates = [request, response]
    for candidate in candidates:
        if candidate is None:
            continue
        redirected = getattr(candidate, "redirected_from", None)
        if redirected is None:
            inner_request = getattr(candidate, "request", None)
            redirected = getattr(inner_request, "redirected_from", None)
        if redirected is not None:
            return _redact_url(str(redirected.url))
    return ""


def _request_is_navigation(request: Any, response: Any | None = None) -> bool:
    for candidate in (request, response):
        if candidate is None:
            continue
        checker = getattr(candidate, "is_navigation_request", None)
        if callable(checker):
            try:
                return bool(checker())
            except Exception:  # noqa: BLE001 - attribution remains optional
                continue
    return False


def _normalize_request_failure(failure: str) -> dict[str, Any]:
    raw_url, separator, detail = failure.partition(" (")
    error = detail[:-1] if separator and detail.endswith(")") else detail
    return {
        "kind": "request_failed",
        "method": "GET",
        "resource_type": "unknown",
        "url": _redact_url(raw_url),
        "frame_url": "",
        "redirected_from": "",
        "same_origin": False,
        "is_navigation": False,
        "status": None,
        "error": error or "unknown failure",
    }


def _copy_request_failure(failure: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": str(failure.get("kind") or "request_failed"),
        "method": str(failure.get("method") or "GET").upper(),
        "resource_type": str(failure.get("resource_type") or "unknown"),
        "url": _redact_url(str(failure.get("url") or "")),
        "frame_url": _redact_url(str(failure.get("frame_url") or "")),
        "redirected_from": _redact_url(str(failure.get("redirected_from") or "")),
        "same_origin": bool(failure.get("same_origin")),
        "is_navigation": bool(failure.get("is_navigation")),
        "status": failure.get("status"),
        "error": str(failure.get("error") or "unknown failure"),
    }


def _deduplicate_failures(failures: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for failure in failures:
        key = (
            failure.get("kind"),
            failure.get("method"),
            failure.get("resource_type"),
            failure.get("url"),
            failure.get("frame_url"),
            failure.get("redirected_from"),
            failure.get("is_navigation"),
            failure.get("status"),
            failure.get("error"),
        )
        if key in unique:
            unique[key]["occurrences"] += 1
        else:
            unique[key] = {**failure, "occurrences": 1}
    return list(unique.values())


def _failure_label(failure: dict[str, Any]) -> str:
    if failure.get("kind") == "http_error":
        return f"HTTP {failure.get('status')} {failure.get('url')}"
    return f"{failure.get('url')} ({failure.get('error')})"


def _same_origin(first: str, second: str) -> bool:
    left = _normalized_origin(first)
    return left is not None and left == _normalized_origin(second)


def _normalized_origin(url: str) -> tuple[str, str, int] | None:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return None
    scheme = parsed.scheme.lower()
    host = parsed.hostname
    if not scheme or not host:
        return None
    if port is None:
        port = {"http": 80, "https": 443, "ws": 80, "wss": 443}.get(scheme, 0)
    return scheme, host, port


def _is_ignorable_failure(
    url: str,
    request_ignores: tuple[re.Pattern[str], ...] = (),
) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https", "ws", "wss"}:
        return True
    return parsed.path.lower().endswith("/favicon.ico") or _matches_any(url, request_ignores)


def _is_ignorable_request_failure(failure: str) -> bool:
    """Intentional aborts are not evidence that a required resource is broken."""

    return "net::ERR_ABORTED" in failure


def _redact_url(url: str) -> str:
    """Keep endpoint identity while removing credentials, query, and fragment."""

    parsed = urlsplit(url)
    if not parsed.scheme:
        return url.split("#", 1)[0].split("?", 1)[0]
    netloc = parsed.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def _is_ignorable_console_error(message: Any) -> bool:
    """Ignore browser-generated transport noise already covered by network evidence."""

    text = str(getattr(message, "text", ""))
    return text.startswith("Failed to load resource: ") or text.startswith(
        "Not allowed to launch '"
    )


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
        failure_count = int(summary["network"].get("failure_count") or len(network_failures))
        unique_failure_count = int(
            summary["network"].get("unique_failure_count") or len(network_failures)
        )
        resource_types = dict(summary["network"].get("failed_resource_type_counts") or {})
        type_summary = ", ".join(
            f"{name}={count}" for name, count in sorted(resource_types.items())
        )
        type_suffix = f" ({type_summary})" if type_summary else ""
        issues.append(
            Issue(
                "resource_failure",
                "error",
                f"{failure_count} request event(s) failed across "
                f"{unique_failure_count} unique endpoint(s){type_suffix}: "
                f"{'; '.join(network_failures[:3])}",
                name,
                "Repair missing, blocked, or failing assets.",
                {
                    "failures": network_failures[:10],
                    "failure_details": list(summary["network"].get("failure_details") or [])[:10],
                    "failure_count": failure_count,
                    "unique_failure_count": unique_failure_count,
                    "failure_kind_counts": dict(
                        summary["network"].get("failure_kind_counts") or {}
                    ),
                    "failed_resource_type_counts": dict(
                        summary["network"].get("failed_resource_type_counts") or {}
                    ),
                },
            )
        )
    overflow = int(data.get("overflowX") or 0)
    if overflow > cfg.overflow_tolerance_px:
        text_scale = float(summary.get("viewport", {}).get("text_scale") or 1.0)
        code = "text_scale_layout_break" if text_scale > 1 else "horizontal_overflow"
        overflowing_elements = list(data.get("overflowingElements") or [])[:5]
        primary = overflowing_elements[0] if overflowing_elements else {}
        message = (
            f"page is {overflow}px wider than the viewport at {text_scale:g}x text scale"
            if text_scale > 1
            else f"page is {overflow}px wider than the viewport"
        )
        issues.append(
            Issue(
                code,
                "error",
                message,
                name,
                "Use max-width, responsive grids, and wrapping instead of fixed widths.",
                {
                    "overflow_px": overflow,
                    "text_scale": text_scale,
                    "selector": str(primary.get("selector") or ""),
                    "label": str(primary.get("label") or ""),
                    "elements": overflowing_elements,
                },
            )
        )
    clipped_text = [
        row
        for row in data.get("clippedText") or []
        if float(row.get("clip_px") or 0) > cfg.text_clip_tolerance_px
    ]
    if clipped_text:
        largest_clip = max(float(row.get("clip_px") or 0) for row in clipped_text)
        issues.append(
            Issue(
                "clipped_text",
                "warning",
                f"{len(clipped_text)} visible text node(s) are clipped by up to "
                f"{largest_clip:g}px",
                name,
                "Remove the fixed overflow boundary, allow the text to wrap, or use an "
                "explicit ellipsis or scroll affordance.",
                {
                    "tolerance_px": cfg.text_clip_tolerance_px,
                    "samples": clipped_text[:5],
                },
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
    safe_area_penetrations = data.get("safeAreaPenetrations") or []
    if safe_area_penetrations:
        required = safe_area_penetrations[0].get("required_gap_px", 0)
        issues.append(
            Issue(
                "bottom_safe_area_penetration",
                "error",
                f"{len(safe_area_penetrations)} bottom-anchored element(s) enter the "
                f"{required}px safe-area band",
                name,
                f"Reserve max({required}px, env(safe-area-inset-bottom)) around bottom controls.",
                {"elements": safe_area_penetrations[:10]},
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
    text_scale = float(summary.get("viewport", {}).get("text_scale") or 1.0)
    # Enlarging every computed font size can trigger responsive reflow inside
    # the page. That reflow is the test action, not an unrelated load shift.
    measured_layout_shift = text_scale == 1.0 and shift.get("supported")
    if measured_layout_shift and clip > cfg.cls_error:
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
    elif measured_layout_shift and clip > cfg.cls_warn:
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
    if readiness.get("load_event_timed_out"):
        issues.append(
            Issue(
                "slow_load_event",
                "warning",
                "page DOM rendered but the load event exceeded its bounded deadline",
                name,
                "Find slow or hanging resources; use a ready_selector when the page is usable "
                "before every asset finishes.",
                {
                    "timeout_ms": readiness.get("load_event_timeout_ms"),
                    "ready_selector": readiness.get("ready_selector"),
                },
            )
        )
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
                "url": _redact_url(str(request.url))[:300],
            }
        )
        route.abort("blockedbyclient")

    safe = cfg.smoke_mode == "safe"
    if safe:
        page.context.route("**/*", block_request)
        page.context.set_offline(True)
    try:
        if cfg.active_smoke_flow:
            result = _run_bounded_flow(page, cfg)
        else:
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
            except Exception as exc:  # noqa: BLE001 - navigation tears down the JS context
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
    if cfg.active_smoke_flow:
        assertion_configured = True
        observed_effect = any(
            step.get("status") == "passed" and step.get("action") in SMOKE_INTERACTION_ACTIONS
            for step in result.get("steps") or []
        )
        success = bool(result.get("assertionMatched"))
        result["kind"] = "flow"
    else:
        assertion_configured = bool(cfg.smoke_success_selector or cfg.smoke_success_url_pattern)
        observed_effect = bool(result.get("changed") or new_page_count or blocked_requests)
        success = bool(result.get("assertionMatched")) if assertion_configured else observed_effect
        result["kind"] = "cta"
    result.update(
        {
            "performed": True,
            "mode": cfg.smoke_mode,
            "offline": safe,
            "viewport": viewport_name,
            "flow_name": cfg.smoke_flow_name,
            "new_page_count": new_page_count,
            "observed_effect": observed_effect,
            "assertion_configured": assertion_configured,
            "assertion_required": bool(cfg.smoke_require_assertion or cfg.active_smoke_flow),
            "success": success,
            "page_error_count": len(actionable_page_errors),
            "page_errors": actionable_page_errors[:10],
            "suppressed_network_errors": suppressed_network_errors[:10],
            "blocked_request_count": len(blocked_requests),
            "blocked_requests": blocked_requests[:10],
        }
    )
    return result


def _run_bounded_flow(page: Any, cfg: Settings) -> dict[str, Any]:
    """Execute a small ordered flow with no arbitrary code or scripting."""

    steps: list[dict[str, Any]] = []
    failed_step: dict[str, Any] | None = None
    for index, step in enumerate(cfg.active_smoke_flow, start=1):
        record: dict[str, Any] = {
            "index": index,
            "action": step.action,
            "status": "passed",
        }
        if step.selector:
            record["selector"] = step.selector
        if step.pattern:
            record["pattern"] = step.pattern
        try:
            if step.action == "click":
                page.locator(step.selector).first.click(timeout=cfg.timeout_ms)
            elif step.action == "fill":
                page.locator(step.selector).first.fill(step.value, timeout=cfg.timeout_ms)
            elif step.action == "press":
                page.locator(step.selector).first.press(step.key, timeout=cfg.timeout_ms)
            elif step.action == "expect_visible":
                page.locator(step.selector).first.wait_for(
                    state="visible",
                    timeout=cfg.timeout_ms,
                )
            elif step.action == "expect_url":
                page.wait_for_url(
                    re.compile(step.pattern, re.IGNORECASE),
                    timeout=cfg.timeout_ms,
                )
            elif step.action == "expect_text":
                locator = page.locator(step.selector).first
                locator.wait_for(state="visible", timeout=cfg.timeout_ms)
                text_source = str(
                    locator.evaluate(
                        "element => ['INPUT', 'TEXTAREA', 'SELECT'].includes(element.tagName)"
                        " ? 'value' : 'text'"
                    )
                )
                if text_source == "value":
                    observed = locator.input_value(timeout=cfg.timeout_ms)
                else:
                    observed = locator.inner_text(timeout=cfg.timeout_ms)
                record["text_source"] = text_source
                record["observed_length"] = len(observed)
                if re.search(step.pattern, observed, re.IGNORECASE) is None:
                    raise AssertionError(
                        f"{text_source} did not match the configured text pattern "
                        f"(observed length: {len(observed)})"
                    )
            if step.action in SMOKE_INTERACTION_ACTIONS and cfg.smoke_settle_ms:
                page.wait_for_timeout(cfg.smoke_settle_ms)
        except Exception as exc:  # noqa: BLE001 - each failed step is report evidence
            record["status"] = "failed"
            record["error"] = str(exc)[:300]
            failed_step = record
        steps.append(record)
        if failed_step is not None:
            break

    assertions = [step for step in steps if step.get("action") in SMOKE_ASSERTION_ACTIONS]
    assertion_matched = failed_step is None and bool(assertions)
    return {
        "found": True,
        "changed": any(step.get("status") == "passed" for step in steps),
        "steps": steps,
        "failedStep": failed_step,
        "assertions": [
            {
                "type": str(step["action"]).removeprefix("expect_"),
                "selector": step.get("selector"),
                "pattern": step.get("pattern"),
                "matched": step.get("status") == "passed",
            }
            for step in assertions
        ],
        "assertionConfigured": True,
        "assertionMatched": assertion_matched,
    }


def _issues_for_smoke(smoke: dict[str, Any]) -> list[Issue]:
    name = str(smoke.get("viewport") or "")
    if smoke.get("kind") == "flow":
        return _issues_for_flow_smoke(smoke, name)
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
        return issues
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


def _issues_for_flow_smoke(smoke: dict[str, Any], viewport: str) -> list[Issue]:
    issues: list[Issue] = []
    if smoke.get("page_error_count"):
        issues.append(
            Issue(
                "smoke_flow_page_error",
                "error",
                "the configured smoke flow raised a JavaScript error",
                viewport,
                "Fix the JavaScript exception before relying on the flow's rendered outcome.",
                {"errors": list(smoke.get("page_errors") or [])[:10]},
            )
        )
    failed_step = smoke.get("failedStep")
    if isinstance(failed_step, dict):
        action = str(failed_step.get("action") or "unknown")
        index = failed_step.get("index")
        is_assertion = action in SMOKE_ASSERTION_ACTIONS
        detail = str(failed_step.get("error") or "step failed")
        evidence = {"step": failed_step, "flow": smoke}
        if is_assertion:
            code = (
                "smoke_flow_text_assertion_failed"
                if action == "expect_text"
                else "smoke_flow_assertion_failed"
            )
            hint = (
                "Make the element's rendered text or form value satisfy the configured "
                "case-insensitive regular expression."
                if action == "expect_text"
                else "Make the expected visible state or URL true after the preceding actions."
            )
            issues.append(
                Issue(
                    code,
                    "error",
                    f"smoke-flow step {index} ({action}) did not satisfy its expectation: {detail}",
                    viewport,
                    hint,
                    evidence,
                )
            )
        else:
            issues.append(
                Issue(
                    "smoke_flow_step_failed",
                    "error",
                    f"smoke-flow step {index} ({action}) could not be executed: {detail}",
                    viewport,
                    "Check the selector, element state, and whether an earlier step "
                    "left the page in the expected state.",
                    evidence,
                )
            )
    elif smoke.get("success") is False:
        issues.append(
            Issue(
                "smoke_flow_assertion_failed",
                "error",
                "the configured smoke flow did not reach a verified assertion",
                viewport,
                "Keep at least one visible-state, text, or URL assertion after an interaction.",
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
