from __future__ import annotations

from typing import Any

import pytest

from ego_webqa.config import Settings
from ego_webqa.engine import _is_ignorable_failure, _issues_for_smoke, _issues_for_viewport


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


def test_private_helpers() -> None:
    assert _is_ignorable_failure("https://example.test/favicon.ico")
    assert not _is_ignorable_failure("https://example.test/app.js")
