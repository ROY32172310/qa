from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from ego_webqa import __version__
from ego_webqa.contracts import load_schema

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_FIXTURES = ROOT / "tests" / "fixtures" / "contracts" / "v1.0"


def test_workflows_keep_matrices_under_strategy() -> None:
    for path in (ROOT / ".github" / "workflows").glob("*.yml"):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(workflow, dict), path
        jobs = workflow.get("jobs")
        assert isinstance(jobs, dict), path
        for job_name, job in jobs.items():
            assert isinstance(job, dict), (path, job_name)
            assert "matrix" not in job, (path, job_name)
            assert "runs-on" in job, (path, job_name)
            strategy = job.get("strategy")
            if isinstance(strategy, dict) and "matrix" in strategy:
                assert isinstance(strategy["matrix"], dict), (path, job_name)


def _bash_executable() -> str:
    if os.name == "nt":
        program_files = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        git_bash = program_files / "Git" / "bin" / "bash.exe"
        if git_bash.is_file():
            return str(git_bash)
    executable = shutil.which("bash")
    if executable is None:
        pytest.skip("bash is required to validate the composite action")
    return executable


def test_composite_action_metadata_and_input_safety() -> None:
    action = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
    assert action["runs"]["using"] == "composite"
    assert action["inputs"]["url"]["required"] is True
    assert action["inputs"]["profile"]["default"] == "baseline"
    assert action["inputs"]["smoke-mode"]["default"] == "safe"
    assert action["inputs"]["smoke-scope"]["default"] == "first"
    assert action["inputs"]["smoke-require-assertion"]["default"] == "false"
    assert action["inputs"]["browser-engine"]["default"] == "chromium"
    assert action["inputs"]["delta-gate"]["default"] == "new"
    assert action["inputs"]["viewport-preset"]["default"] == ""
    assert action["inputs"]["smoke-flow-name"]["default"] == ""

    steps = action["runs"]["steps"]
    install = next(step for step in steps if step.get("name") == "Set up browser")
    assert install["env"]["WEBQA_BROWSER_ENGINE"] == "${{ inputs.browser-engine }}"
    assert 'args=(--browser-engine "$WEBQA_BROWSER_ENGINE")' in install["run"]
    assert "args+=(--with-deps)" in install["run"]
    assert 'ego-webqa setup "${args[@]}"' in install["run"]
    audit = next(step for step in steps if step.get("name") == "Run audit")
    script = audit["run"]
    assert 'python -m ego_webqa "${args[@]}"' in script
    assert "${{ inputs." not in script
    assert audit["env"]["WEBQA_URL"] == "${{ inputs.url }}"
    assert audit["env"]["EGO_WEBQA_HTTP_USERNAME"] == "${{ inputs.http-username }}"
    assert audit["env"]["EGO_WEBQA_HTTP_PASSWORD"] == "${{ inputs.http-password }}"
    assert audit["env"]["WEBQA_BROWSER_ENGINE"] == "${{ inputs.browser-engine }}"
    assert audit["env"]["WEBQA_BASELINE_REPORT"] == "${{ inputs.baseline-report }}"
    assert audit["env"]["WEBQA_VIEWPORT_PRESET"] == "${{ inputs.viewport-preset }}"
    assert audit["env"]["WEBQA_SMOKE_FLOW_NAME"] == "${{ inputs.smoke-flow-name }}"
    assert '--baseline-report "$WEBQA_BASELINE_REPORT"' in script
    assert '--gate "$WEBQA_DELTA_GATE"' in script
    assert '--preset "$WEBQA_VIEWPORT_PRESET"' in script
    assert '--smoke-flow-name "$WEBQA_SMOKE_FLOW_NAME"' in script
    assert "EGO_WEBQA_HTTP_PASSWORD" not in script
    python_step = next(step for step in steps if step.get("name") == "Set up Python")
    assert python_step["uses"] == "actions/setup-python@v7"
    assert any(step.get("uses") == "actions/upload-artifact@v5" for step in steps)
    summary_step = next(step for step in steps if step.get("name") == "Write job summary")
    assert summary_step["if"] == "${{ always() }}"
    assert summary_step["env"]["WEBQA_OUT"] == "${{ inputs.out }}"
    assert "GITHUB_STEP_SUMMARY" in summary_step["run"]
    assert "feedback_bundle.json" in summary_step["run"]
    assert "target URLs, selectors, page text" in summary_step["run"]
    completed = subprocess.run(
        [_bash_executable(), "-n"],
        input=install["run"].encode("utf-8"),
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    # Binary input avoids Windows text-mode CRLF translation, which is not
    # meaningful to the Bash script that GitHub executes with LF endings.
    completed = subprocess.run(
        [_bash_executable(), "-n"],
        input=script.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    summary_script = summary_step["run"]
    completed = subprocess.run(
        [_bash_executable(), "-n"],
        input=summary_script.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")


def test_action_job_summary_renders_only_sanitized_findings(tmp_path: Path) -> None:
    action = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
    step = next(step for step in action["runs"]["steps"] if step.get("name") == "Write job summary")
    output = tmp_path / "out"
    output.mkdir()
    feedback = json.loads((CONTRACT_FIXTURES / "feedback-bundle.json").read_text(encoding="utf-8"))
    feedback["counts"] = {"error": 1, "warning": 2, "root_causes": 1}
    feedback["findings"][0]["viewport_indexes"] = [0, 1]
    feedback["target"] = "https://private.example"
    feedback["findings"][0]["selectors"] = ["#secret"]
    Draft202012Validator(load_schema("feedback-bundle")).validate(feedback)
    (output / "feedback_bundle.json").write_text(
        json.dumps(feedback),
        encoding="utf-8",
    )
    delta = json.loads((CONTRACT_FIXTURES / "delta.json").read_text(encoding="utf-8"))
    delta["gate"]["failed"] = True
    delta["summary"].update({"new": 1, "changed": 2, "resolved": 3})
    Draft202012Validator(load_schema("delta")).validate(delta)
    (output / "delta.json").write_text(
        json.dumps(delta),
        encoding="utf-8",
    )
    github_summary = tmp_path / "step-summary.md"
    script = step["run"].replace("python - ", f'"{sys.executable}" - ', 1)
    completed = subprocess.run(
        [_bash_executable()],
        input=script.encode("utf-8"),
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "WEBQA_OUT": str(output),
            "GITHUB_STEP_SUMMARY": str(github_summary),
            "PYTHONIOENCODING": "cp1252",
        },
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    rendered = github_summary.read_text(encoding="utf-8")
    assert "**Status:** `fail`" in rendered
    assert "1 blocking, 2 warnings, 1 root causes" in rendered
    assert "`horizontal_overflow`" in rendered
    assert "**Baseline gate:** failed (`new`) — 1 new, 2 changed, 3 resolved" in rendered
    assert "private.example" not in rendered
    assert "#secret" not in rendered


def test_example_action_workflow_uses_accessibility_profile() -> None:
    workflow = yaml.safe_load((ROOT / "examples" / "github-action.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["webqa"]["steps"]
    checkout = next(
        step for step in steps if str(step.get("uses", "")).startswith("actions/checkout@")
    )
    action = next(step for step in steps if str(step.get("uses", "")).startswith("ROY32172310/qa@"))
    assert checkout["uses"] == "actions/checkout@v6"
    assert action["uses"] == f"ROY32172310/qa@v{__version__}"
    assert action["with"]["profile"] == "accessibility"
    assert action["with"]["fail-on-warn"] == "true"


def test_readme_action_example_uses_current_runtime_and_release() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "uses: actions/checkout@v6" in readme
    assert f"uses: ROY32172310/qa@v{__version__}" in readme


def test_release_workflow_publishes_github_release_after_pypi_and_registry() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    )
    jobs = workflow["jobs"]

    publish_steps = jobs["publish"]["steps"]
    pypi_step = next(
        step for step in publish_steps if "pypa/gh-action-pypi-publish" in step.get("uses", "")
    )
    assert pypi_step["with"]["skip-existing"] is True

    github_release = jobs["github-release"]
    assert github_release["needs"] == ["publish", "mcp-registry"]
    assert github_release["permissions"]["contents"] == "write"
    assert any(
        step.get("uses") == "actions/download-artifact@v5"
        and step.get("with", {}).get("name") == "python-package"
        for step in github_release["steps"]
    )
    assert any(
        step.get("uses") == "actions/download-artifact@v5"
        and step.get("with", {}).get("name") == "release-extras"
        and step.get("with", {}).get("path") == "dist/agensi/"
        for step in github_release["steps"]
    )

    release_step = next(
        step for step in github_release["steps"] if step.get("name") == "Publish GitHub release"
    )
    script = release_step["run"]
    assert "assets=(dist/*.whl dist/*.tar.gz dist/agensi/*.zip)" in script
    assert 'gh release create "$GITHUB_REF_NAME" "${assets[@]}"' in script
    assert "--verify-tag" in script
    assert 'gh release upload "$GITHUB_REF_NAME" "${assets[@]}"' in script


def test_release_workflow_keeps_non_python_assets_out_of_the_pypi_artifact() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    )
    build_steps = workflow["jobs"]["build"]["steps"]
    artifacts = {
        step["with"]["name"]: step["with"]["path"]
        for step in build_steps
        if step.get("uses") == "actions/upload-artifact@v5"
    }

    assert artifacts["python-package"].splitlines() == [
        "dist/*.whl",
        "dist/*.tar.gz",
    ]
    assert artifacts["release-extras"] == "dist/agensi/*.zip"


def test_release_workflow_publishes_mcp_registry_metadata_after_pypi() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["mcp-registry"]
    assert job["needs"] == "publish"
    assert job["permissions"] == {"contents": "read", "id-token": "write"}
    assert job["env"]["MCP_PUBLISHER_VERSION"] == "v1.8.6"

    script = "\n".join(f"{step.get('if', '')}\n{step.get('run', '')}" for step in job["steps"])
    assert "cosign verify-blob" in script
    assert "mcp-publisher login github-oidc" in script
    assert "mcp-publisher publish" in script
    assert "registry-version.outputs.published != 'true'" in script


def test_ci_exercises_the_composite_action_end_to_end() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["action-smoke"]["steps"]

    assert [step.get("uses") for step in steps].count("./") == 2
    assert any(
        step.get("name") == "Create a baseline through the composite Action"
        and step.get("with", {}).get("viewport-preset") == "quick"
        for step in steps
    )
    assert any(
        step.get("name") == "Gate a second Action run against the baseline"
        and step.get("with", {}).get("delta-gate") == "new"
        for step in steps
    )
    assert any("scripts/verify_action_smoke.py" in step.get("run", "") for step in steps)


def test_release_build_exercises_the_composite_action_end_to_end() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["build"]["steps"]

    assert [step.get("uses") for step in steps].count("./") == 2
    assert any(
        step.get("name") == "Create a release baseline through the composite Action"
        and step.get("with", {}).get("fail-on-warn") == "true"
        for step in steps
    )
    assert any("scripts/verify_action_smoke.py" in step.get("run", "") for step in steps)
