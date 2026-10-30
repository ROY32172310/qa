from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ego_webqa import cli
from ego_webqa.delta import (
    DeltaCompatibilityError,
    compare_reports,
    load_report,
    write_delta,
)


def _issue(
    code: str,
    severity: str,
    *,
    selector: str = "",
    viewport: str = "mobile",
    message: str = "finding",
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = evidence or {}
    if selector:
        payload = {**payload, "selector": selector}
    return {
        "code": code,
        "severity": severity,
        "viewport": viewport,
        "message": message,
        "hint": "",
        "evidence": payload,
        "severity_source": "default",
        "override": {},
    }


def _report(
    issues: list[dict[str, Any]],
    *,
    directory: str = "/tmp/site",
    browser_engine: str = "chromium",
    viewports: list[tuple[int, int, float, int]] | None = None,
) -> dict[str, Any]:
    viewport_values = viewports or [(360, 800, 1.0, 0), (390, 844, 1.5, 34)]
    return {
        "schema_version": "1.0",
        "tool": "ego-webqa",
        "target": "http://127.0.0.1:8000/index.html",
        "status": "fail" if any(item["severity"] == "error" for item in issues) else "pass",
        "counts": {
            "error": sum(item["severity"] == "error" for item in issues),
            "warning": sum(item["severity"] == "warning" for item in issues),
        },
        "started_at": "2026-10-30T00:00:00+00:00",
        "duration_ms": 100,
        "issues": issues,
        "viewports": [
            {
                "viewport": {
                    "name": f"mobile-{index}",
                    "width": width,
                    "height": height,
                    "text_scale": text_scale,
                    "safe_area_bottom_px": safe_area,
                    "has_touch": True,
                }
            }
            for index, (width, height, text_scale, safe_area) in enumerate(viewport_values)
        ],
        "settings": {
            "source": {
                "kind": "directory",
                "directory": directory,
                "file": "index.html",
            },
            "profile": "baseline",
        },
        "runtime": {
            "browser_engine": browser_engine,
            "browser_channel": "chrome",
        },
    }


def test_delta_classifies_stable_root_causes() -> None:
    baseline = _report(
        [
            _issue(
                "dead_primary_cta",
                "error",
                selector="#buy",
                message="CTA did nothing at count 1",
            ),
            _issue("tiny_fonts", "warning", selector="#old", message="old warning"),
        ]
    )
    current = _report(
        [
            _issue(
                "dead_primary_cta",
                "error",
                selector="#buy",
                message="CTA did nothing at count 2",
            ),
            _issue("tiny_fonts", "warning", selector="#new", message="new warning"),
            _issue("huge_overlay", "warning", selector=".modal", message="new warning"),
        ]
    )

    delta = compare_reports(baseline, current)

    assert delta["status"] == "pass"
    assert delta["summary"] == {
        "new": 2,
        "persistent": 1,
        "changed": 0,
        "resolved": 1,
        "total_changes": 4,
        "blocking_regressions": 0,
    }
    persistent = next(
        item for item in delta["changes"] if item["dimension_id"] == "dead_primary_cta"
    )
    assert persistent["change_type"] == "persistent"
    assert persistent["occurrences_before"] == persistent["occurrences_after"] == 1


def test_delta_gate_fails_on_new_or_expanding_blocking_roots() -> None:
    baseline = _report([_issue("tiny_fonts", "warning", selector="#note")])
    current = _report(
        [
            _issue("tiny_fonts", "error", selector="#note", viewport="mobile"),
            _issue("tiny_fonts", "error", selector="#note", viewport="desktop"),
        ]
    )

    delta = compare_reports(baseline, current)

    assert delta["status"] == "fail"
    assert delta["gate"]["failed"] is True
    changed = delta["changes"][0]
    assert changed["change_type"] == "changed"
    assert changed["gate_failed"] is True
    assert changed["block_count_before"] == 0
    assert changed["block_count_after"] == 2


def test_delta_can_report_without_gating() -> None:
    baseline = _report([])
    current = _report([_issue("dead_primary_cta", "error", selector="#buy")])

    delta = compare_reports(baseline, current, gate="none")

    assert delta["status"] == "pass"
    assert delta["gate"] == {"mode": "none", "failed": False}
    assert delta["summary"]["new"] == 1


def test_resource_fingerprint_ignores_volatile_query_strings() -> None:
    baseline = _report(
        [
            _issue(
                "resource_failure",
                "error",
                evidence={
                    "failure_details": [
                        {
                            "url": "https://api.example/data?token=old",
                            "status": 500,
                            "resourceType": "fetch",
                        }
                    ]
                },
            )
        ]
    )
    current = _report(
        [
            _issue(
                "resource_failure",
                "error",
                evidence={
                    "failure_details": [
                        {
                            "url": "https://api.example/data?token=new",
                            "status": 500,
                            "resourceType": "fetch",
                        }
                    ]
                },
            )
        ]
    )

    delta = compare_reports(baseline, current)

    assert delta["summary"]["persistent"] == 1
    assert delta["summary"]["new"] == 0


def test_delta_rejects_incompatible_target_and_configuration() -> None:
    baseline = _report([])
    moved = _report([], directory="/tmp/other")
    with pytest.raises(DeltaCompatibilityError, match="different sources"):
        compare_reports(baseline, moved)

    changed_viewports = _report([], viewports=[(320, 700, 1.0, 0)])
    with pytest.raises(DeltaCompatibilityError, match="different profiles"):
        compare_reports(baseline, changed_viewports)

    changed_browser = _report([], browser_engine="firefox")
    with pytest.raises(DeltaCompatibilityError, match="different browser"):
        compare_reports(baseline, changed_browser)


def test_delta_cli_writes_json_and_returns_gate_status(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    baseline_path.write_text(json.dumps(_report([])), encoding="utf-8")
    current_path.write_text(
        json.dumps(_report([_issue("dead_primary_cta", "error", selector="#buy")])),
        encoding="utf-8",
    )

    assert (
        cli.main(
            [
                "delta",
                "--baseline",
                str(baseline_path),
                "--current",
                str(current_path),
            ]
        )
        == 1
    )
    output = tmp_path / "delta.json"
    assert output.is_file()
    assert "[FAIL] delta gate=new" in capsys.readouterr().out
    assert json.loads(output.read_text(encoding="utf-8"))["summary"]["new"] == 1

    output_path = write_delta(compare_reports(_report([]), _report([])), output)
    assert load_report(output_path)["status"] == "pass"
