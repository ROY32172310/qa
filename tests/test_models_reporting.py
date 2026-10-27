from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from ego_webqa.models import AuditReport, Issue, derive_status
from ego_webqa.reporting import to_junit, to_sarif, write_reports


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
    assert set(artifacts) == {"json", "junit", "sarif"}
    suite = ET.fromstring(to_junit(report))
    assert suite.attrib["tests"] == "1"
    assert len(suite.findall("testcase/failure")) == 1
    sarif = to_sarif(report)
    assert sarif["runs"][0]["results"][0]["ruleId"] == "dead_primary_cta"
