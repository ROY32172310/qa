from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from scripts import dev


def test_subprocess_env_prepends_source_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTHONPATH", str(Path("existing")))
    environment = dev._subprocess_env({"EXTRA": "value"})

    assert environment["PYTHONPATH"] == os.pathsep.join(
        (str(dev.ROOT / "src"), str(Path("existing")))
    )
    assert environment["EXTRA"] == "value"


def test_subprocess_env_sets_source_tree_without_existing_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PYTHONPATH", raising=False)

    assert dev._subprocess_env()["PYTHONPATH"] == str(dev.ROOT / "src")


def test_project_distribution_prefix_matches_pyproject() -> None:
    version = re.search(
        r'(?m)^version = "([^"]+)"$',
        (dev.ROOT / "pyproject.toml").read_text(encoding="utf-8"),
    )
    assert version is not None
    assert dev._project_distribution_prefix() == f"ego_webqa-{version.group(1)}"


def test_main_dispatches_named_task_and_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []

    def task(*arguments: str) -> int:
        called.extend(arguments)
        return 7

    monkeypatch.setitem(dev.TASKS, "example", task)

    assert dev.main(["example", "one", "two"]) == 7
    assert called == ["one", "two"]


def test_main_rejects_missing_or_unknown_task(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert dev.main([]) == 2
    assert dev.main(["missing"]) == 2
    assert "tasks:" in capsys.readouterr().err


def test_typecheck_covers_release_and_verification_scripts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, tuple[str, ...], dict[str, str] | None]] = []

    def run(
        module: str,
        *arguments: str,
        env: dict[str, str] | None = None,
        cwd: Path | None = None,
    ) -> int:
        calls.append((module, arguments, env))
        return 0

    monkeypatch.setattr(dev, "_run", run)

    assert dev.typecheck() == 0
    assert ("mypy", ("scripts",), {"MYPYPATH": "src"}) in calls
