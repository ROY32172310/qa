"""JSON, JUnit XML, and SARIF writers."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .models import AuditReport


def write_reports(report: AuditReport, output_dir: str | Path) -> dict[str, str]:
    """Write all machine-readable artifacts and return their locations."""

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    json_path = out / "report.json"
    junit_path = out / "junit.xml"
    sarif_path = out / "report.sarif"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    junit_path.write_text(to_junit(report), encoding="utf-8")
    sarif_path.write_text(
        json.dumps(to_sarif(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "json": str(json_path),
        "junit": str(junit_path),
        "sarif": str(sarif_path),
    }


def to_junit(report: AuditReport) -> str:
    suite = ET.Element(
        "testsuite",
        {
            "name": "ego-webqa",
            "tests": str(max(1, len(report.issues))),
            "failures": str(sum(issue.severity == "error" for issue in report.issues)),
            "skipped": "0",
            "time": f"{report.duration_ms / 1000:.3f}",
        },
    )
    if not report.issues:
        ET.SubElement(
            suite,
            "testcase",
            {"classname": "ego-webqa", "name": "delivery gate", "time": "0.000"},
        )
    for issue in report.issues:
        case = ET.SubElement(
            suite,
            "testcase",
            {
                "classname": f"ego-webqa.{issue.code}",
                "name": f"{issue.viewport or 'global'}: {issue.code}",
                "time": "0.000",
            },
        )
        if issue.severity == "error":
            failure = ET.SubElement(case, "failure", {"message": issue.message})
            failure.text = issue.hint or issue.message
        else:
            ET.SubElement(case, "system-out").text = issue.message
    return ET.tostring(suite, encoding="unicode", xml_declaration=True)


def to_sarif(report: AuditReport) -> dict[str, Any]:
    rules: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    for issue in report.issues:
        rules.setdefault(
            issue.code,
            {
                "id": issue.code,
                "name": issue.code,
                "shortDescription": {"text": issue.code.replace("_", " ")},
                "help": {"text": issue.hint or "Fix the reported delivery issue."},
            },
        )
        results.append(
            {
                "ruleId": issue.code,
                "level": "error" if issue.severity == "error" else "warning",
                "message": {"text": issue.message},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": report.target},
                        }
                    }
                ],
                "properties": {
                    "viewport": issue.viewport,
                    "evidence": issue.evidence,
                },
            }
        )
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "ego-webqa",
                        "informationUri": "https://github.com/roy/ego-webqa",
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
                "properties": {
                    "status": report.status,
                    "durationMs": report.duration_ms,
                },
            }
        ],
    }
