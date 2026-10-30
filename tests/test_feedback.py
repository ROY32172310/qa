from __future__ import annotations

import json
from pathlib import Path

import pytest

from ego_webqa import cli
from ego_webqa.feedback import build_feedback_bundle


def _raw_report() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "target": "https://private.example/account/secret?token=abc",
        "status": "fail",
        "started_at": "2026-10-30T00:00:00+00:00",
        "duration_ms": 123,
        "issues": [
            {
                "code": "dead_primary_cta",
                "severity": "error",
                "viewport": "private-viewport-name",
                "message": "CTA for Alice did nothing",
                "hint": "Bind the click on private@example.com",
                "evidence": {
                    "selector": "#pay-account-123",
                    "text": "Alice secret balance",
                    "url": "https://private.example/account/secret",
                },
            },
            {
                "code": "tiny_fonts",
                "severity": "warning",
                "viewport": "desktop",
                "message": "Small text",
                "hint": "Increase the font.",
                "evidence": {"selector": ".private-note"},
            },
        ],
        "settings": {
            "source": {
                "kind": "directory",
                "directory": "/home/alice/private-site",
                "file": "index.html",
            },
            "ready_selector": "#private-ready",
            "smoke_selector": "#private-pay",
            "storage_state": "/home/alice/auth.json",
            "browser_engine": "chromium",
        },
        "runtime": {
            "browser_engine": "chromium",
            "browser_channel": "chrome",
            "storage_state": "/home/alice/auth.json",
        },
        "viewports": [
            {
                "viewport": {
                    "name": "private-viewport-name",
                    "width": 360,
                    "height": 800,
                    "text_scale": 1.5,
                    "safe_area_bottom_px": 34,
                    "has_touch": True,
                }
            }
        ],
        "screenshots": ["mobile-private.png"],
    }


def test_feedback_bundle_omits_sensitive_fields_by_default() -> None:
    bundle = build_feedback_bundle(_raw_report())
    serialized = json.dumps(bundle)

    assert bundle["target_kind"] == "local"
    assert bundle["counts"] == {"error": 1, "warning": 1, "root_causes": 2}
    assert bundle["settings"]["source_kind"] == "directory"
    assert bundle["settings"]["ready_selector_configured"] is True
    assert bundle["viewports"][0]["safe_area_bottom_px"] == 34
    assert bundle["viewports"][0]["index"] == 0
    assert bundle["findings"][0]["viewport_indexes"] == [0]
    assert "target" not in bundle
    for secret in (
        "private.example",
        "token=abc",
        "Alice",
        "private@example.com",
        "pay-account-123",
        "/home/alice",
        "mobile-private.png",
        "private-viewport-name",
    ):
        assert secret not in serialized
    assert "selectors" not in bundle["findings"][0]
    assert "messages" not in bundle["findings"][0]


def test_feedback_bundle_explicitly_opt_in_to_context() -> None:
    bundle = build_feedback_bundle(
        _raw_report(),
        include_target=True,
        include_selectors=True,
        include_messages=True,
    )

    assert bundle["target"] == "https://private.example/account/secret?token=abc"
    cta = next(
        finding for finding in bundle["findings"] if finding["dimension_id"] == "dead_primary_cta"
    )
    assert cta["selectors"] == ["#pay-account-123"]
    assert cta["messages"] == ["CTA for Alice did nothing"]
    assert cta["hints"] == ["Bind the click on private@example.com"]
    assert cta["text_snippets"] == ["Alice secret balance"]


def test_feedback_cli_writes_bundle_and_can_print_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(_raw_report()), encoding="utf-8")

    assert cli.main(["feedback", "--report", str(report_path)]) == 0
    output = tmp_path / "feedback_bundle.json"
    assert output.is_file()
    assert str(output) in capsys.readouterr().out
    assert json.loads(output.read_text(encoding="utf-8"))["tool"] == "ego-webqa"

    assert (
        cli.main(
            [
                "feedback",
                "--report",
                str(report_path),
                "--include-target",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["target"].startswith("https://private.example/")


def test_feedback_cli_rejects_invalid_input(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text("{not json", encoding="utf-8")

    assert cli.main(["feedback", "--report", str(report_path)]) == 2
    assert "cannot build feedback bundle" in capsys.readouterr().err
