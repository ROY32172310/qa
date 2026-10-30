from __future__ import annotations

import json
from typing import Any

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from ego_webqa.cli import main
from ego_webqa.contracts import SCHEMA_NAMES, load_schema
from ego_webqa.delta import compare_reports
from ego_webqa.dimensions import registry_payload
from ego_webqa.doctor import DoctorCheck, DoctorReport
from ego_webqa.feedback import build_feedback_bundle
from ego_webqa.models import AuditReport
from ego_webqa.reporting import build_agent_summary


def _report_object() -> AuditReport:
    return AuditReport(
        target="https://example.test/",
        status="pass",
        issues=[],
        viewports=[
            {
                "viewport": {
                    "name": "mobile",
                    "width": 390,
                    "height": 844,
                    "text_scale": 1.0,
                    "safe_area_bottom_px": 0,
                    "has_touch": True,
                }
            }
        ],
        smoke={},
        screenshots=[],
        started_at="2026-10-30T00:00:00+00:00",
        duration_ms=42,
        settings={
            "profile": "baseline",
            "browser_engine": "chromium",
            "browser_channel": "bundled-chromium",
            "smoke_mode": "safe",
            "source": {"kind": "url"},
        },
        runtime={"browser_engine": "chromium", "browser_channel": "bundled-chromium"},
        governance={},
    )


def _validate(name: str, payload: dict[str, Any]) -> None:
    Draft202012Validator(load_schema(name)).validate(payload)


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_every_packaged_schema_is_a_valid_draft_2020_12_schema(name: str) -> None:
    schema = load_schema(name)

    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"].endswith(f"/{name}.schema.json")


def test_core_generated_payloads_validate_against_packaged_schemas() -> None:
    report = _report_object()
    report_payload = report.to_dict()

    _validate("report", report_payload)
    _validate("agent-summary", build_agent_summary(report))
    _validate("dimensions", registry_payload())
    _validate("feedback-bundle", build_feedback_bundle(report_payload))
    _validate("delta", compare_reports(report_payload, report_payload))
    _validate(
        "doctor",
        DoctorReport(
            status="ok",
            checks=(DoctorCheck("python", "ok", "Python 3.11"),),
            runtime={"python": "3.11"},
        ).to_dict(),
    )


def test_schema_rejects_removed_required_field() -> None:
    payload = _report_object().to_dict()
    payload.pop("schema_version")

    with pytest.raises(Exception, match="schema_version"):
        _validate("report", payload)


def test_schema_accepts_optional_fields_added_within_schema_1_0() -> None:
    report = _report_object()
    report_payload = report.to_dict()
    report_payload.pop("governance")
    report_payload["issues"] = [
        {
            "code": "page_error",
            "severity": "error",
            "viewport": "mobile",
            "message": "boom",
            "hint": "",
            "evidence": {},
        }
    ]
    summary = build_agent_summary(report)
    summary.pop("governance")

    _validate("report", report_payload)
    _validate("agent-summary", summary)


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_cli_prints_each_packaged_schema(
    name: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--print-schema", name]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == load_schema(name)
