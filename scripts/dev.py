#!/usr/bin/env python3
"""Cross-platform development tasks for ego-webqa."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST_RESULTS = ROOT / "test-results"


def _subprocess_env(env: dict[str, str] | None = None) -> dict[str, str]:
    merged_env = os.environ.copy()
    source_path = str(ROOT / "src")
    existing = merged_env.get("PYTHONPATH")
    merged_env["PYTHONPATH"] = os.pathsep.join((source_path, existing)) if existing else source_path
    if env:
        merged_env.update(env)
    return merged_env


def _run(
    module: str,
    *arguments: str,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> int:
    command = [sys.executable, "-m", module, *arguments]
    print("+", " ".join(command), flush=True)
    return subprocess.run(
        command,
        cwd=cwd or ROOT,
        env=_subprocess_env(env),
        check=False,
    ).returncode


def _script(path: str, *arguments: str) -> int:
    command = [sys.executable, path, *arguments]
    print("+", " ".join(command), flush=True)
    return subprocess.run(
        command,
        cwd=ROOT,
        env=_subprocess_env(),
        check=False,
    ).returncode


def _project_distribution_prefix() -> str:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    name = re.search(r'(?m)^name = "([^"]+)"$', pyproject)
    version = re.search(r'(?m)^version = "([^"]+)"$', pyproject)
    if name is None or version is None:
        raise RuntimeError("pyproject.toml must declare project name and version")
    normalized_name = re.sub(r"[-_.]+", "_", name.group(1)).lower()
    return f"{normalized_name}-{version.group(1)}"


def test(*arguments: str) -> int:
    return _run("pytest", "-q", *arguments)


def coverage(*arguments: str) -> int:
    TEST_RESULTS.mkdir(exist_ok=True)
    return _run(
        "pytest",
        "-q",
        "--junitxml=test-results/pytest.xml",
        "--cov=ego_webqa",
        "--cov-branch",
        "--cov-report=term-missing",
        "--cov-report=xml",
        "--cov-report=json",
        "--cov-fail-under=90",
        *arguments,
    )


def lint() -> int:
    return _run("ruff", "check", ".")


def format_check() -> int:
    return _run("black", "--check", ".")


def typecheck(*arguments: str) -> int:
    source = _run("mypy", *arguments)
    if source:
        return source
    scripts = _run("mypy", *arguments, "scripts", env={"MYPYPATH": "src"})
    if scripts:
        return scripts
    benchmark = _run("mypy", *arguments, "benchmarks", env={"MYPYPATH": "src"})
    if benchmark:
        return benchmark
    return _run("mypy", *arguments, "dogfood", env={"MYPYPATH": "src"})


def benchmark(*arguments: str) -> int:
    return _script("benchmarks/run.py", *arguments)


def dogfood(*arguments: str) -> int:
    return _script("dogfood/run.py", *arguments)


def package(*arguments: str) -> int:
    # A local build/ directory otherwise shadows the installed build package
    # when Python resolves the ``-m build`` entry point from the repository.
    with tempfile.TemporaryDirectory(prefix="ego-webqa-build-") as directory:
        build = _run("build", *arguments, str(ROOT), cwd=Path(directory))
    if build:
        return build
    prefix = _project_distribution_prefix()
    artifacts = [
        str(path.relative_to(ROOT))
        for path in sorted((ROOT / "dist").iterdir())
        if path.name.startswith(prefix) and path.suffix in {".whl", ".gz"}
    ]
    if not artifacts:
        print("package: build produced no distributions", file=sys.stderr)
        return 2
    return _run("twine", "check", *artifacts)


def agensi_package(*arguments: str) -> int:
    return _script("scripts/package_agensi.py", *arguments)


def check() -> int:
    for task in (lint, format_check, typecheck, coverage):
        result = task()
        if result:
            return result
    return 0


def full() -> int:
    result = check()
    if result:
        return result
    return benchmark()


TASKS = {
    "test": test,
    "coverage": coverage,
    "lint": lint,
    "format-check": format_check,
    "typecheck": typecheck,
    "benchmark": benchmark,
    "dogfood": dogfood,
    "package": package,
    "agensi-package": agensi_package,
    "check": check,
    "full": full,
}


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] in {"-h", "--help", "list"}:
        print("usage: python scripts/dev.py <task> [task arguments]")
        print("tasks:", ", ".join(TASKS))
        return 0 if arguments else 2
    task_name, *task_arguments = arguments
    task = TASKS.get(task_name)
    if task is None:
        print(f"unknown task: {task_name}", file=sys.stderr)
        print("tasks:", ", ".join(TASKS), file=sys.stderr)
        return 2
    try:
        return task(*task_arguments)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
