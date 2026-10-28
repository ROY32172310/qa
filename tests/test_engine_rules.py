from __future__ import annotations

import re
from typing import Any

import pytest

from ego_webqa.config import Settings
from ego_webqa.engine import (
    _is_blocked_network_error,
    _is_ignorable_console_error,
    _is_ignorable_failure,
    _is_ignorable_request_failure,
    _issues_for_smoke,
    _issues_for_viewport,
    _network_summary,
    _redact_url,
    _should_run_smoke,
)


def _summary(**updates: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "overflowX": 0,
        "textLength": 100,
        "elementCount": 10,
        "tinyFonts": [],
        "smallTargets": [],
        "hugeOverlays": [],
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
    codes = _codes(_issues_for_viewport(summary, Settings()))
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
        "failure_count": 0,
    }


def test_custom_protocol_launch_failures_are_not_resource_failures() -> None:
    summary = _network_summary(
        [],
        ["openapp.example://product/42 (net::ERR_ABORTED)"],
    )
    assert summary["failures"] == []
    assert summary["failure_count"] == 0


def test_network_evidence_redacts_credentials_and_query_parameters() -> None:
    class Request:
        def sizes(self) -> dict[str, int]:
            return {"responseBodySize": 42}

    class Response:
        url = "https://preview-user:secret@example.test/app.js?token=top-secret#debug"
        status = 500
        request = Request()

    summary = _network_summary([Response()], [])
    serialized = str(summary)
    assert summary["failures"] == ["HTTP 500 https://example.test/app.js"]
    assert "secret" not in serialized
    assert "token" not in serialized
    assert _redact_url(Response.url) == "https://example.test/app.js"


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
