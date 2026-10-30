from __future__ import annotations

import json
import re
from pathlib import Path
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

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_FIXTURES = ROOT / "tests" / "fixtures" / "contracts" / "v1.0"
_SEMVER = re.compile(r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)$")


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


def _assert_deprecation_annotations(node: Any, path: str = "$") -> None:
    if isinstance(node, dict):
        if node.get("deprecated") is True:
            metadata = node.get("x-ego-webqa-deprecation")
            assert isinstance(metadata, dict), f"{path}: deprecated field needs metadata"
            deprecated_in = metadata.get("deprecated_in")
            remove_no_earlier_than = metadata.get("remove_no_earlier_than")
            assert isinstance(deprecated_in, str), f"{path}: missing deprecated_in"
            assert isinstance(
                remove_no_earlier_than, str
            ), f"{path}: missing remove_no_earlier_than"
            deprecated_match = _SEMVER.fullmatch(deprecated_in)
            removal_match = _SEMVER.fullmatch(remove_no_earlier_than)
            assert deprecated_match is not None, f"{path}: invalid deprecated_in"
            assert removal_match is not None, f"{path}: invalid remove_no_earlier_than"
            deprecated_index = int(deprecated_match["major"]) * 1000 + int(
                deprecated_match["minor"]
            )
            removal_index = int(removal_match["major"]) * 1000 + int(removal_match["minor"])
            assert (
                removal_index - deprecated_index >= 2
            ), f"{path}: removal must be at least two minor releases later"
        for key, value in node.items():
            _assert_deprecation_annotations(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _assert_deprecation_annotations(value, f"{path}[{index}]")


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_every_packaged_schema_is_a_valid_draft_2020_12_schema(name: str) -> None:
    schema = load_schema(name)

    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"].endswith(f"/{name}.schema.json")


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_schema_deprecations_honor_the_two_minor_release_window(name: str) -> None:
    _assert_deprecation_annotations(load_schema(name))


def test_deprecation_validation_rejects_a_short_removal_window() -> None:
    schema = {
        "properties": {
            "legacy": {
                "deprecated": True,
                "x-ego-webqa-deprecation": {
                    "deprecated_in": "0.8.0",
                    "remove_no_earlier_than": "0.9.0",
                },
            }
        }
    }

    with pytest.raises(AssertionError, match="two minor releases"):
        _assert_deprecation_annotations(schema)


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


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_frozen_v1_payload_remains_valid(name: str) -> None:
    payload = json.loads((CONTRACT_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))

    _validate(name, payload)


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
