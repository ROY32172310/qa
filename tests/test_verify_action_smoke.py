from __future__ import annotations

import json
from pathlib import Path

from scripts import verify_action_smoke


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _report() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "status": "pass",
        "viewports": [{}, {}, {}, {}],
        "smoke_runs": [{"success": True}],
    }


def test_action_smoke_verifier_accepts_complete_outputs(
    tmp_path: Path,
    capsys,
) -> None:
    baseline = tmp_path / "baseline"
    current = tmp_path / "current"
    _write_json(baseline / "report.json", _report())
    _write_json(current / "report.json", _report())
    _write_json(current / "feedback_bundle.json", {"status": "pass"})
    _write_json(
        current / "delta.json",
        {"schema_version": "1.0", "gate": {"mode": "new", "failed": False}},
    )
    summary = tmp_path / "summary.md"
    summary.write_text(
        "## ego-webqa delivery QA\n"
        "**Baseline gate:** passed (`new`)\n"
        "## ego-webqa delivery QA\n"
        "Review `feedback_bundle.json` before sharing.\n",
        encoding="utf-8",
    )

    assert (
        verify_action_smoke.main(
            [
                "--baseline-dir",
                str(baseline),
                "--current-dir",
                str(current),
                "--summary",
                str(summary),
            ]
        )
        == 0
    )
    assert "action-smoke: pass" in capsys.readouterr().out


def test_action_smoke_verifier_rejects_failed_delta_gate(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    current = tmp_path / "current"
    _write_json(baseline / "report.json", _report())
    _write_json(current / "report.json", _report())
    _write_json(current / "feedback_bundle.json", {"status": "pass"})
    _write_json(
        current / "delta.json",
        {"schema_version": "1.0", "gate": {"mode": "new", "failed": True}},
    )
    summary = tmp_path / "summary.md"
    summary.write_text("not reached", encoding="utf-8")

    assert (
        verify_action_smoke.main(
            [
                "--baseline-dir",
                str(baseline),
                "--current-dir",
                str(current),
                "--summary",
                str(summary),
            ]
        )
        == 2
    )
