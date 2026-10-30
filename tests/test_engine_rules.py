from __future__ import annotations

import re
from typing import Any

import pytest

from ego_webqa.config import Settings, Viewport
from ego_webqa.engine import (
    AuditRuntimeError,
    _apply_text_scale,
    _collect_snapshot,
    _downgrade_partial_navigation_timeouts,
    _goto_document,
    _has_transient_navigation_timeout,
    _is_blocked_network_error,
    _is_ignorable_console_error,
    _is_ignorable_failure,
    _is_ignorable_request_failure,
    _issues_for_smoke,
    _issues_for_viewport,
    _launch_browser,
    _network_summary,
    _redact_url,
    _request_failure_record,
    _same_origin,
    _should_run_smoke,
    _trace_stage,
    _transient_execution_retry_reason,
    _wait_for_dom_content_loaded,
)
from ego_webqa.models import AuditReport, Issue


def _summary(**updates: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "overflowX": 0,
        "textLength": 100,
        "elementCount": 10,
        "tinyFonts": [],
        "smallTargets": [],
        "hugeOverlays": [],
        "clippedText": [],
        "brokenImages": [],
        "distortedMedia": [],
    }
    data.update(updates.pop("measurements", {}))
    summary: dict[str, Any] = {
        "viewport": {"name": "mobile"},
        "http_status": 200,
        "page_errors": [],
        "console_errors": [],
        "network": {
            "failures": [],
            "failure_count": 0,
            "transfer_bytes": 20_000,
            "request_count": 4,
        },
        "timing": {
            "firstContentfulPaintMs": 100,
            "layoutShift": {"supported": True, "clip": 0, "maxShift": 0, "shifts": 0},
        },
        "measurements": data,
    }
    summary.update(updates)
    return summary


def _codes(issues: list[Any]) -> set[str]:
    return {issue.code for issue in issues}


def test_stage_trace_is_opt_in(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("EGO_WEBQA_TRACE", raising=False)
    _trace_stage("mobile", "probe", 0)
    assert capsys.readouterr().err == ""

    monkeypatch.setenv("EGO_WEBQA_TRACE", "1")
    _trace_stage("mobile", "probe", 0)
    assert "[ego-webqa trace] mobile: probe (" in capsys.readouterr().err


def test_viewport_rule_buckets_and_thresholds() -> None:
    summary = _summary(
        console_errors=["boom"],
        page_errors=["ReferenceError"],
        network={
            "failures": ["HTTP 404 /asset.js"],
            "failure_count": 1,
            "transfer_bytes": 500_000,
            "request_count": 31,
        },
        timing={
            "firstContentfulPaintMs": 4_000,
            "layoutShift": {"supported": True, "clip": 0.2, "maxShift": 0.2, "shifts": 2},
        },
        measurements={
            "overflowX": 30,
            "tinyFonts": [{"label": str(i), "px": 8} for i in range(4)]
            + [{"label": str(i), "px": 11} for i in range(4)],
            "smallTargets": [{"label": "x", "width": 20, "height": 20}] * 4,
            "hugeOverlays": [{"label": "mask"}],
            "brokenImages": [{"src": "/missing.png"}],
            "distortedMedia": [{"label": "canvas", "deviation": 0.3}],
        },
    )
    issues = _issues_for_viewport(summary, Settings())
    codes = _codes(issues)
    assert {
        "console_error",
        "page_error",
        "resource_failure",
        "horizontal_overflow",
        "unreadable_font",
        "tiny_fonts",
        "small_tap_targets",
        "huge_overlay",
        "broken_image",
        "media_distortion",
        "slow_first_paint",
        "layout_shift",
        "transfer_budget",
    } <= codes
    resource_issue = next(issue for issue in issues if issue.code == "resource_failure")
    assert "1 request event(s) failed across 1 unique endpoint(s)" in resource_issue.message


def test_text_scale_reflow_is_not_reported_as_page_layout_shift() -> None:
    summary = _summary(
        viewport={"name": "mobile-150", "text_scale": 1.5},
        timing={
            "firstContentfulPaintMs": 100,
            "layoutShift": {"supported": True, "clip": 0.5, "maxShift": 0.5, "shifts": 2},
        },
    )

    assert [issue.code for issue in _issues_for_viewport(summary, Settings())] == []


def test_clipped_text_uses_the_configured_tolerance() -> None:
    summary = _summary(
        measurements={
            "clippedText": [
                {
                    "label": "Account status",
                    "selector": "#status",
                    "clipped_by": "#status-card",
                    "clip_px": 12.5,
                },
                {
                    "label": "Round-off only",
                    "selector": "#rounding",
                    "clipped_by": "#rounding-card",
                    "clip_px": 1,
                },
            ]
        }
    )
    issues = _issues_for_viewport(summary, Settings())
    assert _codes(issues) == {"clipped_text"}
    issue = issues[0]
    assert issue.severity == "warning"
    assert issue.evidence["tolerance_px"] == 1.5
    assert issue.evidence["samples"] == [
        {
            "label": "Account status",
            "selector": "#status",
            "clipped_by": "#status-card",
            "clip_px": 12.5,
        }
    ]

    assert _codes(_issues_for_viewport(summary, Settings(text_clip_tolerance_px=13))) == set()


class _NavigationPage:
    def __init__(self) -> None:
        self.calls = 0

    def goto(self, *_: Any, **__: Any) -> str:
        self.calls += 1
        return "response"


class _FailingPage:
    def __init__(self) -> None:
        self.calls = 0

    def goto(self, *_: Any, **__: Any) -> None:
        self.calls += 1
        raise RuntimeError("browser disconnected")


def test_navigation_uses_commit_and_reports_one_attempt() -> None:
    page = _NavigationPage()

    assert _goto_document(page, "https://example.com", 100) == ("response", 1)
    assert page.calls == 1


def test_navigation_does_not_retry_non_timeout_errors() -> None:
    page = _FailingPage()

    with pytest.raises(RuntimeError, match="browser disconnected"):
        _goto_document(page, "https://example.com", 100)
    assert page.calls == 1


class _FakeLaunch:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, Any]] = []

    def launch(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("missing browser")
        return f"browser-{kwargs.get('channel', 'bundled')}"


class _FakePlaywright:
    def __init__(
        self,
        *,
        chromium_fail: bool = False,
        firefox_fail: bool = False,
        webkit_fail: bool = False,
    ) -> None:
        self.chromium = _FakeLaunch(fail=chromium_fail)
        self.firefox = _FakeLaunch(fail=firefox_fail)
        self.webkit = _FakeLaunch(fail=webkit_fail)


def test_browser_launcher_selects_each_playwright_engine() -> None:
    playwright = _FakePlaywright()

    assert _launch_browser(playwright, "chromium", "") == ("browser-bundled", "bundled-chromium")
    assert _launch_browser(playwright, "chromium", "msedge") == ("browser-msedge", "msedge")
    assert _launch_browser(playwright, "firefox", "") == (
        "browser-bundled",
        "bundled-firefox",
    )
    assert _launch_browser(playwright, "webkit", "") == ("browser-bundled", "bundled-webkit")


def test_browser_launcher_explains_missing_preview_engines() -> None:
    playwright = _FakePlaywright(firefox_fail=True, webkit_fail=True)
    with pytest.raises(AuditRuntimeError, match="playwright install firefox"):
        _launch_browser(playwright, "firefox", "")
    with pytest.raises(AuditRuntimeError, match="playwright install webkit"):
        _launch_browser(playwright, "webkit", "")


def test_dom_content_loaded_timeout_is_non_fatal() -> None:
    class SlowDocument:
        def wait_for_load_state(self, *_: Any, **__: Any) -> None:
            raise TimeoutError("domcontentloaded timed out")

    assert _wait_for_dom_content_loaded(SlowDocument(), 100) is False


class _RacingTextScalePage:
    def __init__(self) -> None:
        self.evaluate_calls = 0
        self.wait_calls = 0

    def wait_for_selector(self, *_: Any, **__: Any) -> None:
        self.wait_calls += 1

    def evaluate(self, *_: Any, **__: Any) -> dict[str, Any]:
        self.evaluate_calls += 1
        if self.evaluate_calls == 1:
            raise RuntimeError("Execution context was destroyed")
        return {"applied": True, "textScale": 1.5, "scaledElements": 12}

    def wait_for_timeout(self, *_: Any, **__: Any) -> None:
        return None


def test_text_scale_retries_after_navigation_race() -> None:
    page = _RacingTextScalePage()

    result = _apply_text_scale(page, 1.5, 1_000)

    assert result["applied"] is True
    assert page.wait_calls == 2
    assert page.evaluate_calls == 2


class _RacingSnapshotPage:
    def __init__(self, *, recover: bool) -> None:
        self.recover = recover
        self.evaluate_calls = 0
        self.wait_calls = 0

    def evaluate(self, *_: Any, **__: Any) -> dict[str, Any]:
        self.evaluate_calls += 1
        if not self.recover or self.evaluate_calls == 1:
            raise TypeError("Cannot read properties of null (reading 'scrollWidth')")
        return {"viewport": {"width": 360, "height": 800}, "textLength": 10}

    def wait_for_timeout(self, _: int) -> None:
        self.wait_calls += 1


def test_snapshot_retries_across_document_replacement() -> None:
    page = _RacingSnapshotPage(recover=True)

    result = _collect_snapshot(page, Settings(), Viewport(360, 800))

    assert result["textLength"] == 10
    assert page.evaluate_calls == 2
    assert page.wait_calls == 1


def test_snapshot_fails_cleanly_when_document_never_stabilizes() -> None:
    page = _RacingSnapshotPage(recover=False)

    with pytest.raises(RuntimeError, match="page DOM did not stabilize"):
        _collect_snapshot(page, Settings(), Viewport(360, 800))

    assert page.evaluate_calls == 3
    assert page.wait_calls == 2


def test_transient_navigation_timeout_requests_fresh_retry() -> None:
    summary = _summary(
        status="error",
        error='Page.goto: Timeout 15000ms exceeded.\nwaiting until "commit"',
    )
    report = AuditReport(
        target="https://example.com",
        status="fail",
        issues=[],
        viewports=[summary],
        smoke={},
        screenshots=[],
        started_at="2026-10-29T00:00:00+00:00",
        duration_ms=1,
        settings={},
    )

    assert _has_transient_navigation_timeout(report) is True


@pytest.mark.parametrize(
    "error",
    [
        "document root did not become ready for text scaling: timeout",
        "page DOM did not stabilize for measurement: document root or body was not available",
    ],
)
def test_document_replacement_requests_fresh_retry(error: str) -> None:
    report = AuditReport(
        target="https://example.com",
        status="fail",
        issues=[],
        viewports=[_summary(status="error", error=error)],
        smoke={},
        screenshots=[],
        started_at="2026-10-29T00:00:00+00:00",
        duration_ms=1,
        settings={},
    )

    assert _transient_execution_retry_reason(report) == "document_replacement"


def test_isolated_navigation_timeout_becomes_incomplete_warning() -> None:
    issues = [
        Issue("load_error", "error", "page could not be audited", "mobile", evidence={"x": 1})
    ]
    viewports = [
        {
            "viewport": {"name": "mobile"},
            "status": "error",
            "error": "Page.goto: Timeout 15000ms exceeded",
        },
        {"viewport": {"name": "desktop"}, "status": "ok"},
    ]

    result = _downgrade_partial_navigation_timeouts(issues, viewports)

    assert result[0].severity == "warning"
    assert result[0].evidence == {
        "x": 1,
        "partial_navigation_timeout": True,
        "successful_viewports": 1,
    }


def test_navigation_failure_remains_blocking_when_every_viewport_fails() -> None:
    issues = [
        Issue("load_error", "error", "page could not be audited", "mobile", evidence={"x": 1})
    ]
    viewports = [
        {
            "viewport": {"name": "mobile"},
            "status": "error",
            "error": "Page.goto: Timeout 15000ms exceeded",
        }
    ]

    result = _downgrade_partial_navigation_timeouts(issues, viewports)

    assert result[0].severity == "error"


def test_blank_page_is_an_error() -> None:
    issues = _issues_for_viewport(
        _summary(measurements={"textLength": 2, "elementCount": 2}),
        Settings(),
    )
    assert [issue.code for issue in issues] == ["blank_page"]
    assert issues[0].severity == "error"


@pytest.mark.parametrize(
    ("bytes_used", "requests", "severity"),
    [
        (400_001, 4, "warning"),
        (20_000, 31, "warning"),
        (1_500_001, 4, "error"),
        (20_000, 61, "error"),
    ],
)
def test_transfer_budget_bands(bytes_used: int, requests: int, severity: str) -> None:
    issues = _issues_for_viewport(
        _summary(
            network={
                "failures": [],
                "failure_count": 0,
                "transfer_bytes": bytes_used,
                "request_count": requests,
            }
        ),
        Settings(),
    )
    assert [(issue.code, issue.severity) for issue in issues] == [("transfer_budget", severity)]


def test_smoke_classification() -> None:
    assert [issue.code for issue in _issues_for_smoke({"found": False})] == [
        "primary_cta_not_found"
    ]
    assert [
        issue.code
        for issue in _issues_for_smoke(
            {"found": True, "label": "Buy", "changed": False, "new_page_count": 0}
        )
    ] == ["dead_primary_cta"]
    assert (
        _issues_for_smoke({"found": True, "label": "Buy", "changed": True, "new_page_count": 0})
        == []
    )
    assert (
        _issues_for_smoke(
            {
                "found": True,
                "label": "Buy",
                "changed": False,
                "new_page_count": 0,
                "blocked_request_count": 1,
            }
        )
        == []
    )
    assert [
        issue.code
        for issue in _issues_for_smoke(
            {
                "found": True,
                "label": "Buy",
                "changed": False,
                "page_error_count": 1,
            }
        )
    ] == ["cta_page_error"]
    assert [
        issue.code
        for issue in _issues_for_smoke(
            {
                "found": True,
                "label": "Buy",
                "changed": True,
                "success": False,
                "assertion_configured": True,
                "assertions": [{"type": "selector", "selector": "#success", "matched": False}],
            }
        )
    ] == ["cta_assertion_failed"]
    assert (
        _issues_for_smoke(
            {
                "found": True,
                "label": "Buy",
                "changed": False,
                "success": True,
                "assertion_configured": True,
            }
        )
        == []
    )


def test_smoke_flow_classification_names_step_and_page_errors() -> None:
    issues = _issues_for_smoke(
        {
            "kind": "flow",
            "viewport": "mobile",
            "success": False,
            "page_error_count": 1,
            "page_errors": ["Error: boom"],
            "failedStep": {
                "index": 2,
                "action": "click",
                "selector": "#missing",
                "status": "failed",
                "error": "selector not found",
            },
        }
    )
    assert [issue.code for issue in issues] == [
        "smoke_flow_page_error",
        "smoke_flow_step_failed",
    ]
    assert "step 2 (click)" in issues[1].message


def test_smoke_flow_failed_assertion_and_unreached_verification_are_blocking() -> None:
    assertion = _issues_for_smoke(
        {
            "kind": "flow",
            "viewport": "mobile",
            "success": False,
            "failedStep": {
                "index": 3,
                "action": "expect_visible",
                "selector": "#success",
                "status": "failed",
                "error": "timeout",
            },
        }
    )
    assert [issue.code for issue in assertion] == ["smoke_flow_assertion_failed"]
    assert all(issue.severity == "error" for issue in assertion)

    unreached = _issues_for_smoke(
        {"kind": "flow", "viewport": "mobile", "success": False, "failedStep": None}
    )
    assert [issue.code for issue in unreached] == ["smoke_flow_assertion_failed"]


def test_smoke_flow_text_assertion_has_a_specific_blocking_dimension() -> None:
    issues = _issues_for_smoke(
        {
            "kind": "flow",
            "viewport": "mobile",
            "success": False,
            "failedStep": {
                "index": 2,
                "action": "expect_text",
                "selector": "#count",
                "pattern": "^1$",
                "status": "failed",
                "text_source": "text",
                "observed_length": 1,
                "error": "text did not match the configured text pattern",
            },
        }
    )
    assert [issue.code for issue in issues] == ["smoke_flow_text_assertion_failed"]
    assert issues[0].severity == "error"
    assert "case-insensitive regular expression" in issues[0].hint


def test_private_helpers() -> None:
    assert _is_ignorable_failure("https://example.test/favicon.ico")
    assert _is_ignorable_failure("openapp.example://product/42")
    assert not _is_ignorable_failure("https://example.test/app.js")
    assert _is_ignorable_failure(
        "https://example.test/analytics/error.js",
        (re.compile(r"/analytics/"),),
    )
    assert _is_blocked_network_error("TypeError: Failed to fetch")
    assert not _is_blocked_network_error("ReferenceError: checkout is not defined")
    assert _same_origin("https://example.test/app.js", "https://EXAMPLE.test:443/page")
    assert not _same_origin("http://example.test/app.js", "https://example.test/page")


def test_browser_transport_noise_is_not_double_counted_as_console_error() -> None:
    class Message:
        def __init__(self, text: str) -> None:
            self.text = text

    assert _is_ignorable_console_error(
        Message("Failed to load resource: the server responded with a status of 403")
    )
    assert _is_ignorable_console_error(Message("Not allowed to launch 'openapp://product'"))
    assert not _is_ignorable_console_error(Message("TypeError: checkout is not defined"))
    assert _is_ignorable_request_failure("https://example.test/cancel (net::ERR_ABORTED)")
    assert not _is_ignorable_request_failure(
        "https://example.test/missing.js (net::ERR_FILE_NOT_FOUND)"
    )


def test_ignored_requests_do_not_count_toward_budget() -> None:
    class Request:
        def __init__(self, size: int) -> None:
            self._size = size

        def sizes(self) -> dict[str, int]:
            return {"responseBodySize": self._size}

    class Response:
        def __init__(self, url: str, status: int, size: int) -> None:
            self.url = url
            self.status = status
            self.request = Request(size)

    summary = _network_summary(
        [
            Response("https://example.test/app.js", 200, 42),
            Response("https://example.test/analytics/collect", 500, 1_000_000),
        ],
        ["https://example.test/analytics/collect (net::ERR_FAILED)"],
        (re.compile(r"/analytics/"),),
    )
    assert summary == {
        "request_count": 1,
        "ignored_request_count": 1,
        "transfer_bytes": 42,
        "failures": [],
        "failure_details": [],
        "failure_count": 0,
        "unique_failure_count": 0,
        "failure_kind_counts": {},
        "failed_resource_type_counts": {},
    }


def test_custom_protocol_launch_failures_are_not_resource_failures() -> None:
    summary = _network_summary(
        [],
        ["openapp.example://product/42 (net::ERR_ABORTED)"],
    )
    assert summary["failures"] == []
    assert summary["failure_count"] == 0


def test_network_evidence_redacts_credentials_and_query_parameters() -> None:
    class Frame:
        url = "https://preview-user:secret@example.test/page?session=secret"

    class Redirect:
        url = "https://preview-user:secret@old.example.test/app.js?token=secret"

    class Request:
        method = "GET"
        resource_type = "script"
        frame = Frame()
        redirected_from = Redirect()

        def sizes(self) -> dict[str, int]:
            return {"responseBodySize": 42}

        def is_navigation_request(self) -> bool:
            return False

    class Response:
        url = "https://preview-user:secret@example.test/app.js?token=top-secret#debug"
        status = 500
        request = Request()

    summary = _network_summary([Response()], [])
    serialized = str(summary)
    assert summary["failures"] == ["HTTP 500 https://example.test/app.js"]
    detail = summary["failure_details"][0]
    assert detail["resource_type"] == "script"
    assert detail["frame_url"] == "https://example.test/page"
    assert detail["redirected_from"] == "https://old.example.test/app.js"
    assert detail["same_origin"] is True
    assert detail["status"] == 500
    assert detail["occurrences"] == 1
    assert summary["unique_failure_count"] == 1
    assert "secret" not in serialized
    assert "token" not in serialized
    assert _redact_url(Response.url) == "https://example.test/app.js"


def test_request_failure_evidence_is_structured_deduplicated_and_attributed() -> None:
    class Frame:
        url = "https://example.test/page?token=secret"

    class Redirect:
        url = "https://example.test/start?token=secret"

    class Request:
        url = "https://cdn.example.test/app.js?token=secret"
        method = "GET"
        resource_type = "script"
        frame = Frame()
        redirected_from = Redirect()
        failure = "net::ERR_BLOCKED_BY_ORB"

        def is_navigation_request(self) -> bool:
            return False

    record = _request_failure_record(Request())
    summary = _network_summary([], [record, record])
    assert summary["failure_count"] == 2
    assert summary["failures"] == ["https://cdn.example.test/app.js (net::ERR_BLOCKED_BY_ORB)"]
    detail = summary["failure_details"][0]
    assert detail["kind"] == "request_failed"
    assert detail["resource_type"] == "script"
    assert detail["frame_url"] == "https://example.test/page"
    assert detail["redirected_from"] == "https://example.test/start"
    assert detail["same_origin"] is False
    assert detail["occurrences"] == 2
    assert summary["unique_failure_count"] == 1
    assert summary["failure_kind_counts"] == {"request_failed": 2}
    assert summary["failed_resource_type_counts"] == {"script": 2}
    assert "secret" not in str(summary)


def test_network_idle_timeout_is_visible_as_warning() -> None:
    summary = _summary(readiness={"network_idle_timed_out": True})
    issues = _issues_for_viewport(summary, Settings(timeout_ms=5_000))
    assert [(issue.code, issue.severity) for issue in issues] == [
        ("network_idle_timeout", "warning")
    ]


def test_slow_load_event_is_advisory_when_dom_rendered() -> None:
    summary = _summary(
        readiness={
            "dom_content_loaded": True,
            "load_event_timed_out": True,
            "load_event_timeout_ms": 3_000,
        }
    )
    issues = _issues_for_viewport(summary, Settings())
    assert [(issue.code, issue.severity) for issue in issues] == [("slow_load_event", "warning")]


def test_smoke_scope_controls_viewport_runs() -> None:
    assert _should_run_smoke(Settings(), 0)
    assert not _should_run_smoke(Settings(), 1)
    assert _should_run_smoke(Settings(smoke_scope="all"), 0)
    assert _should_run_smoke(Settings(smoke_scope="all"), 4)
