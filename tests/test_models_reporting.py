from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from ego_webqa.dimensions import DIMENSIONS, dimension_for, registry_payload
from ego_webqa.models import AuditReport, Issue, derive_status
from ego_webqa.reporting import (
    SCOPE_STATEMENT,
    build_agent_summary,
    to_junit,
    to_sarif,
    write_reports,
)


def _report(issues: list[Issue]) -> AuditReport:
    return AuditReport(
        target="http://127.0.0.1:8000/",
        status=derive_status(issues),
        issues=issues,
        viewports=[],
        smoke={},
        screenshots=[],
        started_at="2026-10-27T00:00:00+00:00",
        duration_ms=120,
        settings={},
    )


def test_status_precedence() -> None:
    assert derive_status([]) == "pass"
    assert derive_status([Issue("x", "warning", "warn")]) == "warn"
    assert derive_status([Issue("x", "warning", "warn")], fail_on_warn=True) == "fail"
    assert derive_status([Issue("x", "error", "bad")]) == "fail"


def test_machine_report_formats(tmp_path: Path) -> None:
    issue = Issue("dead_primary_cta", "error", "CTA did nothing", "mobile", "Bind the click.")
    report = _report([issue])
    artifacts = write_reports(report, tmp_path)
    payload = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert payload["tool"] == "ego-webqa"
    assert payload["counts"] == {"error": 1, "warning": 0}
    assert set(artifacts) == {"json", "agent_summary", "junit", "sarif"}
    assert Path(artifacts["agent_summary"]).is_file()
    suite = ET.fromstring(to_junit(report))
    assert suite.attrib["tests"] == "1"
    assert len(suite.findall("testcase/failure")) == 1
    sarif = to_sarif(report)
    assert sarif["runs"][0]["results"][0]["ruleId"] == "dead_primary_cta"
    assert (
        sarif["runs"][0]["tool"]["driver"]["informationUri"] == "https://github.com/ROY32172310/qa"
    )


def test_warning_and_empty_junit() -> None:
    warning = Issue("small_tap_targets", "warning", "Too small")
    suite = ET.fromstring(to_junit(_report([warning])))
    assert suite.findtext("testcase/system-out") == "Too small"
    assert suite.attrib["failures"] == "0"

    empty = ET.fromstring(to_junit(_report([])))
    assert empty.find("testcase").attrib["name"] == "delivery gate"


def test_dimension_registry_is_closed_and_versioned() -> None:
    assert DIMENSIONS
    assert all(code == dimension.id for code, dimension in DIMENSIONS.items())
    assert all(dimension.version for dimension in DIMENSIONS.values())
    payload = registry_payload()
    assert payload["schema_version"] == "1.0"
    assert [row["id"] for row in payload["dimensions"]] == sorted(DIMENSIONS)
    assert dimension_for("horizontal_overflow").default_severity == "block"
    assert dimension_for("huge_overlay").version == "1.1.0"
    assert dimension_for("media_distortion").version == "1.1.0"
    assert "aspect_min_rendered_px" in dimension_for("media_distortion").parameters
    assert dimension_for("missing_html_lang").profile == "accessibility"
    with pytest.raises(ValueError, match="unregistered"):
        dimension_for("not_a_dimension")


def test_agent_summary_aggregates_root_causes_and_reproduction() -> None:
    issues = [
        Issue(
            "dead_primary_cta",
            "error",
            "CTA did nothing",
            "mobile",
            "Bind the click.",
            {"selector": "#buy", "text": "Buy"},
        ),
        Issue(
            "dead_primary_cta",
            "error",
            "CTA did nothing",
            "desktop",
            "Bind the click.",
            {"selector": "#buy", "text": "Buy"},
        ),
        Issue("tiny_fonts", "warning", "Small secondary text", "mobile", "Increase the font."),
    ]
    report = AuditReport(
        target="https://example.com/preview",
        status="fail",
        issues=issues,
        viewports=[
            {
                "viewport": {
                    "name": "mobile",
                    "width": 390,
                    "height": 844,
                    "text_scale": 1.5,
                    "safe_area_bottom_px": 34,
                }
            },
            {
                "viewport": {
                    "name": "desktop",
                    "width": 1280,
                    "height": 800,
                }
            },
        ],
        screenshots=[],
        started_at="2026-10-28T00:00:00+00:00",
        duration_ms=120,
        settings={
            "profile": "accessibility",
            "ready_selector": "#app-ready",
            "smoke_selector": "#buy",
            "browser_channel": "chrome",
        },
        smoke={"enabled": False},
    )
    summary = build_agent_summary(report)
    assert summary["status"] == "fail"
    assert summary["scope_statement"] == SCOPE_STATEMENT
    assert summary["summary"]["total_block"] == 2
    assert summary["summary"]["total_warn"] == 1
    assert summary["summary"]["unique_root_causes"] == 2
    cta = summary["failed_items"][0]
    assert cta["dimension_id"] == "dead_primary_cta"
    assert cta["selector"] == "#buy"
    assert cta["text_snippet"] == "Buy"
    assert cta["occurrences"] == 2
    assert cta["problems"] == ["CTA did nothing"]
    assert cta["evidence_by_viewport"] == {
        "mobile": [{"selector": "#buy", "text": "Buy"}],
        "desktop": [{"selector": "#buy", "text": "Buy"}],
    }
    assert "390x844:mobile@1.5~34" in cta["reproduce"]
    assert "1280x800:desktop" in cta["reproduce"]
    assert "--profile accessibility" in cta["reproduce"]
    assert "--ready-selector '#app-ready'" in cta["reproduce"]
    assert "--smoke-selector '#buy'" in cta["reproduce"]
    assert "--browser-channel chrome" in cta["reproduce"]
    assert "--no-smoke" in cta["reproduce"]


def test_agent_summary_reproduction_uses_local_source_directory() -> None:
    report = _report([Issue("ready_selector_not_found", "error", "Not ready", "mobile")])
    report.settings = {
        "source": {
            "kind": "directory",
            "directory": "/tmp/generated-site",
            "file": "home.html",
            "config": "/tmp/webqa.json",
        },
        "ready_selector": "#app-ready",
    }

    reproduce = build_agent_summary(report)["failed_items"][0]["reproduce"]
    assert "ego-webqa --dir /tmp/generated-site --file home.html" in reproduce
    assert "--config /tmp/webqa.json" in reproduce
    assert "--ready-selector '#app-ready'" in reproduce
    assert "http://127.0.0.1:8000/" not in reproduce


def test_agent_summary_preserves_distinct_network_problems_and_viewport_evidence() -> None:
    report = _report(
        [
            Issue(
                "resource_failure",
                "error",
                "1 request event failed",
                "mobile",
                evidence={"failure_details": [{"url": "https://api.example/mobile"}]},
            ),
            Issue(
                "resource_failure",
                "error",
                "12 request events failed",
                "desktop",
                evidence={"failure_details": [{"url": "https://api.example/desktop"}]},
            ),
        ]
    )
    item = build_agent_summary(report)["failed_items"][0]
    assert item["problem"] == "1 request event failed (+1 related finding(s))"
    assert item["problems"] == ["1 request event failed", "12 request events failed"]
    assert (
        item["evidence_by_viewport"]["desktop"][0]["failure_details"][0]["url"]
        == "https://api.example/desktop"
    )


def test_agent_summary_reproduction_preserves_audit_settings() -> None:
    report = _report([Issue("dead_primary_cta", "error", "CTA did nothing", "mobile")])
    report.settings = {
        "source": {"kind": "url", "config": "/tmp/webqa.json"},
        "profile": "accessibility",
        "timeout_ms": 9_000,
        "ready_selector": "#app-ready",
        "wait_for_network_idle": True,
        "ignore_selectors": [".noise"],
        "ignore_console_patterns": ["known warning"],
        "ignore_request_patterns": ["analytics"],
        "smoke_selector": "#buy",
        "smoke_success_selector": "#success",
        "smoke_success_url_pattern": "/complete",
        "smoke_scope": "all",
        "smoke_settle_ms": 1_200,
        "smoke_require_assertion": True,
        "smoke_mode": "live",
        "browser_channel": "chrome",
        "fail_on_warn": True,
    }
    report.smoke = {"enabled": True}

    reproduce = build_agent_summary(report)["failed_items"][0]["reproduce"]
    expected_fragments = [
        "--config /tmp/webqa.json",
        "--profile accessibility",
        "--timeout-ms 9000",
        "--ready-selector '#app-ready'",
        "--wait-for-network-idle",
        "--ignore-selector .noise",
        "--ignore-console-pattern 'known warning'",
        "--ignore-request-pattern analytics",
        "--smoke-selector '#buy'",
        "--smoke-success-selector '#success'",
        "--smoke-success-url-pattern /complete",
        "--smoke-scope all",
        "--smoke-settle-ms 1200",
        "--smoke-require-assertion",
        "--smoke-mode live",
        "--browser-channel chrome",
        "--fail-on-warn",
    ]
    for fragment in expected_fragments:
        assert fragment in reproduce
    assert "--no-smoke" not in reproduce
