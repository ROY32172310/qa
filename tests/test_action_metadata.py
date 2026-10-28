from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_composite_action_metadata_and_input_safety() -> None:
    action = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
    assert action["runs"]["using"] == "composite"
    assert action["inputs"]["url"]["required"] is True
    assert action["inputs"]["profile"]["default"] == "baseline"
    assert action["inputs"]["smoke-mode"]["default"] == "safe"

    steps = action["runs"]["steps"]
    audit = next(step for step in steps if step.get("name") == "Run audit")
    script = audit["run"]
    assert 'python -m ego_webqa "${args[@]}"' in script
    assert "${{ inputs." not in script
    assert audit["env"]["WEBQA_URL"] == "${{ inputs.url }}"
    assert any(step.get("uses") == "actions/upload-artifact@v4" for step in steps)
    subprocess.run(["bash", "-n"], input=script, text=True, check=True)


def test_example_action_workflow_uses_accessibility_profile() -> None:
    workflow = yaml.safe_load((ROOT / "examples" / "github-action.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["webqa"]["steps"]
    action = next(step for step in steps if str(step.get("uses", "")).startswith("ROY"))
    assert action["with"]["profile"] == "accessibility"
    assert action["with"]["fail-on-warn"] == "true"
