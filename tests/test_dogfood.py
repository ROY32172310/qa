from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from dogfood import run
from ego_webqa.config import SmokeStep

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "dogfood" / "cases.json"
VARIABLES = {
    "EGO_ROOT": Path("/srv/projects/ego"),
    "EGO_PROJECT_SPACE": Path("/data/projects/ego/workspace"),
}


def test_shipped_manifest_is_complete_and_diverse() -> None:
    manifest = run.load_manifest(MANIFEST, VARIABLES)

    assert manifest.name == "ego-real-pages-2026-10-29"
    assert len(manifest.cases) == 20
    assert len({case.id for case in manifest.cases}) == 20
    assert sum(case.kind == "url" for case in manifest.cases) == 14
    flow_cases = {case.id: case for case in manifest.cases if case.smoke_flow}
    assert set(flow_cases) == {
        "ego-public-math-practice",
        "ego-generated-noodle-shop",
        "ego-generated-click-counter",
        "ego-generated-games-gallery",
    }
    assert all(case.smoke for case in flow_cases.values())
    assert all(len(case.smoke_flow) == 2 for case in flow_cases.values())
    categories = {category for case in manifest.cases for category in case.categories}
    assert {
        "authentication",
        "commerce",
        "dashboard",
        "form",
        "game",
        "landing",
        "learning",
        "mobile",
        "pwa",
        "spa",
        "tool",
    } <= categories


def test_manifest_expands_local_placeholders(tmp_path: Path) -> None:
    manifest_path = tmp_path / "cases.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "name": "test",
                "defaults": {"profile": "baseline", "smoke": False},
                "cases": [
                    {
                        "id": "local",
                        "kind": "local",
                        "directory": "${EGO_ROOT}/pages",
                        "file": "index.html",
                        "categories": ["landing"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = run.load_manifest(manifest_path, {"EGO_ROOT": tmp_path})

    assert manifest.cases[0].directory == str((tmp_path / "pages").resolve())
    assert manifest.cases[0].source().endswith("pages/index.html")


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda case: case.update({"unknown": True}), "unknown key"),
        (lambda case: case.update({"kind": "file"}), "kind must be"),
        (lambda case: case.update({"directory": "${MISSING}/pages"}), "unresolved"),
        (lambda case: case.update({"url": "https://example.com"}), "cannot define a URL"),
        (lambda case: case.update({"smoke_flow": []}), "non-empty list"),
        (
            lambda case: case.update({"smoke_flow": [{"action": "click", "selector": ".button"}]}),
            "requires an expect_visible, expect_url, or expect_text assertion",
        ),
        (
            lambda case: case.update(
                {
                    "smoke_flow": [
                        {"action": "eval", "selector": "body"},
                        {"action": "expect_visible", "selector": "body"},
                    ]
                }
            ),
            "action must be one of",
        ),
    ],
)
def test_manifest_rejects_invalid_cases(
    tmp_path: Path,
    mutate: Callable[[dict[str, object]], None],
    message: str,
) -> None:
    case: dict[str, object] = {
        "id": "local",
        "kind": "local",
        "directory": "${EGO_ROOT}/pages",
        "file": "index.html",
        "categories": ["landing"],
    }
    mutate(case)
    manifest_path = tmp_path / "cases.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "name": "test",
                "cases": [case],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(run.DogfoodConfigError, match=message):
        run.load_manifest(manifest_path, {"EGO_ROOT": tmp_path})


def test_audit_command_uses_public_cli_and_disables_smoke(tmp_path: Path) -> None:
    case = run.DogfoodCase(
        "page",
        "local",
        ("landing",),
        "",
        "baseline",
        False,
        directory="/tmp/site",
        file="index.html",
    )

    command = run.audit_command("python", case, tmp_path)

    assert command[:3] == ["python", "-m", "ego_webqa"]
    assert command[-5:] == ["--no-smoke", "--dir", "/tmp/site", "--file", "index.html"]
    assert str(tmp_path) in command


def test_audit_command_uses_case_config_for_bounded_flow(tmp_path: Path) -> None:
    flow = (
        SmokeStep("click", selector=".add-btn"),
        SmokeStep("expect_visible", selector="#cartItems .cart-item"),
    )
    case = run.DogfoodCase(
        "page",
        "local",
        ("commerce",),
        "",
        "baseline",
        True,
        smoke_flow=flow,
        directory="/tmp/site",
        file="index.html",
    )

    command = run.audit_command("python", case, tmp_path)

    config_index = command.index("--config")
    assert command[config_index + 1] == str(tmp_path / run.DOGFOOD_CONFIG_NAME)
    assert "--no-smoke" not in command
    assert command[-4:] == ["--dir", "/tmp/site", "--file", "index.html"]


def test_run_case_writes_flow_config_and_uses_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    flow = (
        SmokeStep("fill", selector="#search", value="no-match"),
        SmokeStep("expect_visible", selector="#empty"),
    )
    case = run.DogfoodCase(
        "page",
        "url",
        ("interactive",),
        "",
        "baseline",
        True,
        smoke_flow=flow,
        url="https://example.com",
    )
    captured: dict[str, object] = {}

    def fail_fast(
        command: list[str], _stdout: object, _stderr: object, _timeout: int
    ) -> tuple[bool, int]:
        captured["command"] = command
        return False, 2

    monkeypatch.setattr(run, "_execute_audit", fail_fast)

    result = run._run_case(1, 1, case, tmp_path, "", 1_000)

    config_path = tmp_path / "cases" / "page" / run.DOGFOOD_CONFIG_NAME
    assert captured["command"] == result["command"]
    assert "--config" in result["command"]
    assert "--no-smoke" not in result["command"]
    assert result["smoke_mode"] == "bounded_flow"
    assert result["smoke_flow_steps"] == 2
    assert Path("cases") / "page" / run.DOGFOOD_CONFIG_NAME in {
        Path(item) for item in result["artifacts"]
    }
    assert json.loads(config_path.read_text(encoding="utf-8")) == {
        "smoke_flow": [
            {"action": "fill", "selector": "#search", "value": "no-match"},
            {"action": "expect_visible", "selector": "#empty"},
        ]
    }


def test_metrics_use_nearest_rank_runtime_and_count_findings() -> None:
    results = [
        {
            "kind": "local",
            "status": "pass",
            "wall_duration_ms": duration,
            "issue_count": issues,
            "finding_codes": codes,
        }
        for duration, issues, codes in (
            (100, 0, []),
            (200, 1, ["overflow"]),
            (300, 2, ["overflow", "dead_primary_cta"]),
        )
    ]
    results.append(
        {
            "kind": "url",
            "wall_duration_ms": 9_999,
            "runtime_error": "failed",
        }
    )

    metrics = run._metrics(results)

    assert metrics["successful_audits"] == 3
    assert metrics["runtime_errors"] == 1
    assert metrics["completion_rate"] == 0.75
    assert metrics["total_issues"] == 3
    assert metrics["runtime_ms"] == {"count": 3, "p50": 200, "p95": 300, "max": 300}
    assert metrics["finding_codes"] == {"dead_primary_cta": 1, "overflow": 2}
    assert metrics["by_source"]["local"] == {
        "cases": 3,
        "successful_audits": 3,
        "runtime_errors": 0,
        "completion_rate": 1.0,
        "runtime_ms": {"count": 3, "p50": 200, "p95": 300, "max": 300},
    }
    assert metrics["by_source"]["url"] == {
        "cases": 1,
        "successful_audits": 0,
        "runtime_errors": 1,
        "completion_rate": 0.0,
        "runtime_ms": {"count": 0, "p50": None, "p95": None, "max": None},
    }


def test_markdown_keeps_public_and_local_runtime_groups_separate() -> None:
    manifest = run.DogfoodManifest(Path("cases.json"), "sha", "sample", ())
    results = [
        {
            "id": "public",
            "kind": "url",
            "status": "pass",
            "wall_duration_ms": 900,
            "issue_count": 0,
            "finding_codes": [],
            "smoke_mode": "disabled",
            "categories": ["landing"],
        },
        {
            "id": "local",
            "kind": "local",
            "status": "warn",
            "wall_duration_ms": 200,
            "issue_count": 1,
            "finding_codes": ["tiny_fonts"],
            "smoke_mode": "disabled",
            "categories": ["tool"],
        },
    ]

    markdown = run._render_markdown(manifest, results)

    assert "Execution profile: `real-world-mixed`" in markdown
    assert "Latency role: `observational`" in markdown
    assert "| public URL | 1 | 1 | 0 | 100.00% | 900/900/900 ms |" in markdown
    assert "| local artifact | 1 | 1 | 0 | 100.00% | 200/200/200 ms |" in markdown


def test_case_timeout_is_recorded_without_killing_the_batch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    case = run.DogfoodCase(
        "page",
        "url",
        ("landing",),
        "",
        "baseline",
        False,
        url="https://example.com",
    )

    monkeypatch.setattr(run, "_execute_audit", lambda *_: (True, -15))

    result = run._run_case(1, 1, case, tmp_path, "", 1_000)

    assert result["runtime_error"] == "case exceeded 1000ms deadline"
    artifact_names = {Path(path).name for path in result["artifacts"]}
    assert {"stdout.log", "stderr.log"} <= artifact_names


def test_audit_deadline_kills_descendant_processes(tmp_path: Path) -> None:
    marker = tmp_path / "heartbeat.txt"
    child = tmp_path / "child.py"
    parent = tmp_path / "parent.py"
    child.write_text(
        "import sys, time\n"
        "from pathlib import Path\n"
        "path = Path(sys.argv[1])\n"
        "while True:\n"
        "    with path.open('a', encoding='utf-8') as handle:\n"
        "        handle.write('x')\n"
        "        handle.flush()\n"
        "    time.sleep(0.05)\n",
        encoding="utf-8",
    )
    parent.write_text(
        "import subprocess, sys, time\n"
        "subprocess.Popen(\n"
        "    [sys.executable, sys.argv[1], sys.argv[2]],\n"
        "    stdout=subprocess.DEVNULL,\n"
        "    stderr=subprocess.DEVNULL,\n"
        ")\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    stdout_path = tmp_path / "stdout.log"
    stderr_path = tmp_path / "stderr.log"
    started = time.monotonic()

    with (
        stdout_path.open("wb") as stdout_file,
        stderr_path.open("wb") as stderr_file,
    ):
        timed_out, returncode = run._execute_audit(
            [sys.executable, str(parent), str(child), str(marker)],
            stdout_file,
            stderr_file,
            2_000,
        )

    assert timed_out
    assert returncode is not None
    assert time.monotonic() - started < (10 if sys.platform == "win32" else 5)
    size_at_return = marker.stat().st_size
    assert size_at_return > 0
    time.sleep(0.3)
    assert marker.stat().st_size == size_at_return
