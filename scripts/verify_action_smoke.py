#!/usr/bin/env python3
"""Verify the real GitHub composite Action smoke outputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def verify(baseline_dir: Path, current_dir: Path, summary_path: Path) -> None:
    baseline_report = _load_json(baseline_dir / "report.json")
    current_report = _load_json(current_dir / "report.json")
    feedback = _load_json(current_dir / "feedback_bundle.json")
    delta = _load_json(current_dir / "delta.json")
    summary = summary_path.read_text(encoding="utf-8")

    for label, report in (("baseline", baseline_report), ("current", current_report)):
        if report.get("schema_version") != "1.0":
            raise ValueError(f"{label} report must use schema_version 1.0")
        if report.get("status") != "pass":
            raise ValueError(f"{label} report must pass the clean fixture")
        viewports = report.get("viewports")
        if not isinstance(viewports, list) or len(viewports) != 4:
            raise ValueError(f"{label} report must use the four-variant quick preset")
        smoke_runs = report.get("smoke_runs")
        if not isinstance(smoke_runs, list) or not any(
            isinstance(run, dict) and run.get("success") is True for run in smoke_runs
        ):
            raise ValueError(f"{label} report must contain a successful explicit smoke assertion")

    if feedback.get("status") != "pass":
        raise ValueError("feedback bundle must record a passing current audit")
    if "http://127.0.0.1:8765" in json.dumps(feedback, sort_keys=True):
        raise ValueError("feedback bundle must not expose the target URL")

    if delta.get("schema_version") != "1.0":
        raise ValueError("delta must use schema_version 1.0")
    gate = delta.get("gate")
    if not isinstance(gate, dict) or gate.get("mode") != "new" or gate.get("failed") is not False:
        raise ValueError("baseline delta gate must pass in new mode")

    if summary.count("## ego-webqa delivery QA") != 2:
        raise ValueError("both Action invocations must append a job summary")
    if "**Baseline gate:** passed (`new`)" not in summary:
        raise ValueError("job summary must report the passing baseline gate")
    if "Review `feedback_bundle.json` before sharing." not in summary:
        raise ValueError("job summary must retain the privacy warning")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--current-dir", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    arguments = parser.parse_args(argv)

    try:
        verify(arguments.baseline_dir, arguments.current_dir, arguments.summary)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        message = str(exc).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"action-smoke: {exc}", file=sys.stderr)
        print(f"::error title=action-smoke::{message}")
        return 2
    print("action-smoke: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
