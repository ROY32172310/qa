#!/usr/bin/env python3
"""Run ego-webqa against the curated real-world dogfood sample."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import platform
import signal
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from ego_webqa import __version__  # noqa: E402
from ego_webqa.config import Settings, SmokeStep  # noqa: E402

MANIFEST_SCHEMA_VERSION = "1.0"
DOGFOOD_CONFIG_NAME = "smoke-config.json"
_CASE_KEYS = {
    "id",
    "kind",
    "url",
    "directory",
    "file",
    "categories",
    "notes",
    "profile",
    "smoke",
    "smoke_flow",
}


class DogfoodConfigError(ValueError):
    """The dogfood manifest is invalid or cannot be resolved."""


@dataclass(frozen=True, slots=True)
class DogfoodCase:
    id: str
    kind: str
    categories: tuple[str, ...]
    notes: str
    profile: str
    smoke: bool
    smoke_flow: tuple[SmokeStep, ...] = ()
    url: str = ""
    directory: str = ""
    file: str = ""

    def source(self) -> str:
        if self.kind == "url":
            return self.url
        return f"{self.directory}/{self.file}"


@dataclass(frozen=True, slots=True)
class DogfoodManifest:
    path: Path
    sha256: str
    name: str
    cases: tuple[DogfoodCase, ...]


def _required_string(value: Mapping[str, Any], key: str, label: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise DogfoodConfigError(f"{label} requires a non-empty {key}")
    return item.strip()


def _optional_string(value: Mapping[str, Any], key: str, default: str = "") -> str:
    item = value.get(key, default)
    if not isinstance(item, str):
        raise DogfoodConfigError(f"{key} must be a string")
    return item


def _strings(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise DogfoodConfigError(f"{label} must be a non-empty list")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise DogfoodConfigError(f"{label} must contain non-empty strings")
    return tuple(item.strip() for item in value)


def _smoke_flow(value: Any, label: str) -> tuple[SmokeStep, ...]:
    if not isinstance(value, list) or not value:
        raise DogfoodConfigError(f"{label} smoke_flow must be a non-empty list")
    try:
        flow = tuple(SmokeStep.from_mapping(item) for item in value)
        Settings(smoke_flow=flow)
    except ValueError as exc:
        raise DogfoodConfigError(f"{label} smoke_flow is invalid: {exc}") from exc
    return flow


def _expand_path(value: str, variables: Mapping[str, Path], label: str) -> Path:
    expanded = value
    for name, path in variables.items():
        expanded = expanded.replace(f"${{{name}}}", str(path))
    if "${" in expanded:
        raise DogfoodConfigError(f"{label} contains an unresolved environment placeholder")
    return Path(expanded).expanduser().resolve()


def load_manifest(path: str | Path, variables: Mapping[str, Path]) -> DogfoodManifest:
    """Load a manifest and resolve local paths without touching target pages."""

    manifest_path = Path(path).resolve()
    try:
        raw_bytes = manifest_path.read_bytes()
        raw = json.loads(raw_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise DogfoodConfigError(f"cannot load manifest {manifest_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise DogfoodConfigError("manifest root must be an object")
    if raw.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise DogfoodConfigError(f"manifest schema_version must be {MANIFEST_SCHEMA_VERSION!r}")
    name = _required_string(raw, "name", "manifest")
    defaults = raw.get("defaults", {})
    if not isinstance(defaults, dict):
        raise DogfoodConfigError("manifest defaults must be an object")
    raw_cases = raw.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise DogfoodConfigError("manifest must contain at least one case")

    cases: list[DogfoodCase] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_cases, start=1):
        label = f"case #{index}"
        if not isinstance(item, dict):
            raise DogfoodConfigError(f"{label} must be an object")
        unknown = sorted(set(item) - _CASE_KEYS)
        if unknown:
            raise DogfoodConfigError(f"{label} contains unknown key(s): {', '.join(unknown)}")
        case_id = _required_string(item, "id", label)
        if case_id in seen:
            raise DogfoodConfigError(f"duplicate case id {case_id!r}")
        seen.add(case_id)
        kind = _required_string(item, "kind", f"case {case_id!r}")
        if kind not in {"url", "local"}:
            raise DogfoodConfigError(f"case {case_id!r} kind must be 'url' or 'local'")
        profile = _optional_string(
            item, "profile", _optional_string(defaults, "profile", "baseline")
        )
        if profile not in {"baseline", "accessibility"}:
            raise DogfoodConfigError(f"case {case_id!r} profile must be baseline or accessibility")
        smoke = item.get("smoke", defaults.get("smoke", False))
        if type(smoke) is not bool:
            raise DogfoodConfigError(f"case {case_id!r} smoke must be a boolean")
        raw_smoke_flow = item.get("smoke_flow")
        smoke_flow = (
            _smoke_flow(raw_smoke_flow, f"case {case_id!r}") if raw_smoke_flow is not None else ()
        )
        smoke = smoke or bool(smoke_flow)
        categories = _strings(item.get("categories"), f"case {case_id!r} categories")
        notes = _optional_string(item, "notes")
        if kind == "url":
            url = _required_string(item, "url", f"case {case_id!r}")
            if "directory" in item or "file" in item:
                raise DogfoodConfigError(f"URL case {case_id!r} cannot define a local file")
            cases.append(
                DogfoodCase(
                    case_id,
                    kind,
                    categories,
                    notes,
                    profile,
                    smoke,
                    smoke_flow,
                    url=url,
                )
            )
            continue
        directory = _expand_path(
            _required_string(item, "directory", f"case {case_id!r}"),
            variables,
            f"case {case_id!r} directory",
        )
        file_name = _optional_string(item, "file", "index.html")
        if not file_name:
            raise DogfoodConfigError(f"local case {case_id!r} requires a file")
        if "url" in item:
            raise DogfoodConfigError(f"local case {case_id!r} cannot define a URL")
        cases.append(
            DogfoodCase(
                case_id,
                kind,
                categories,
                notes,
                profile,
                smoke,
                smoke_flow,
                directory=str(directory),
                file=file_name,
            )
        )
    return DogfoodManifest(
        manifest_path,
        hashlib.sha256(raw_bytes).hexdigest(),
        name,
        tuple(cases),
    )


def audit_command(
    python: str,
    case: DogfoodCase,
    output_dir: Path,
    browser_channel: str = "",
) -> list[str]:
    """Build the public CLI invocation so dogfooding exercises the shipped surface."""

    command = [
        python,
        "-m",
        "ego_webqa",
        "--out",
        str(output_dir),
        "--profile",
        case.profile,
    ]
    if browser_channel:
        command.extend(["--browser-channel", browser_channel])
    if case.smoke_flow:
        command.extend(["--config", str(output_dir / DOGFOOD_CONFIG_NAME)])
    elif not case.smoke:
        command.append("--no-smoke")
    if case.kind == "url":
        command.append(case.url)
    else:
        command.extend(["--dir", case.directory, "--file", case.file])
    return command


def _subprocess_env() -> dict[str, str]:
    environment = os.environ.copy()
    source = str(ROOT / "src")
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = f"{source}{os.pathsep}{existing}" if existing else source
    return environment


def _json_file(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return raw


def _terminate_process_tree(process: subprocess.Popen[Any]) -> None:
    """Stop an audit and every browser process started in its process group."""

    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
    else:
        killpg = cast(Callable[[int, int], None], cast(Any, os).killpg)
        sigterm = cast(int, getattr(signal, "SIGTERM", 15))
        sigkill = cast(int, getattr(signal, "SIGKILL", 9))
        with contextlib.suppress(ProcessLookupError, PermissionError):
            killpg(process.pid, sigterm)
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=2)
        # Descendants can outlive their group leader. Kill the group before
        # returning even when the direct process exited after SIGTERM.
        with contextlib.suppress(ProcessLookupError, PermissionError):
            killpg(process.pid, sigkill)
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def _execute_audit(
    command: Sequence[str],
    stdout_file: Any,
    stderr_file: Any,
    timeout_ms: int,
) -> tuple[bool, int | None]:
    """Run one CLI audit with a deadline that covers its whole process tree."""

    popen_options: dict[str, Any] = {}
    if os.name == "nt":
        popen_options["creationflags"] = getattr(
            subprocess,
            "CREATE_NEW_PROCESS_GROUP",
            0,
        )
    else:
        popen_options["start_new_session"] = True
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=_subprocess_env(),
        stdout=stdout_file,
        stderr=stderr_file,
        **popen_options,
    )
    try:
        return False, process.wait(timeout=timeout_ms / 1000)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        return True, process.returncode


def _run_case(
    index: int,
    total: int,
    case: DogfoodCase,
    output: Path,
    browser: str,
    case_timeout_ms: int,
) -> dict[str, Any]:
    case_dir = output / "cases" / case.id
    case_dir.mkdir(parents=True, exist_ok=True)
    before = set(case_dir.iterdir())
    if case.smoke_flow:
        _write_smoke_config(case, case_dir)
    command = audit_command(sys.executable, case, case_dir, browser)
    stdout_path = case_dir / "stdout.log"
    stderr_path = case_dir / "stderr.log"
    smoke_metadata = {
        "smoke_mode": (
            "bounded_flow" if case.smoke_flow else "auto_cta" if case.smoke else "disabled"
        ),
        "smoke_flow_steps": len(case.smoke_flow),
    }
    started = time.monotonic()
    timed_out = False
    try:
        with (
            stdout_path.open("wb") as stdout_file,
            stderr_path.open("wb") as stderr_file,
        ):
            timed_out, returncode = _execute_audit(
                command,
                stdout_file,
                stderr_file,
                case_timeout_ms,
            )
    except OSError as exc:
        stdout = stdout_path.read_text(encoding="utf-8", errors="replace")[-4_000:]
        stderr = stderr_path.read_text(encoding="utf-8", errors="replace")[-4_000:]
        return {
            "id": case.id,
            "categories": list(case.categories),
            "kind": case.kind,
            "source": case.source(),
            "notes": case.notes,
            **smoke_metadata,
            "command": command,
            "exit_code": None,
            "wall_duration_ms": round((time.monotonic() - started) * 1000),
            "runtime_error": f"cannot start audit: {exc}",
            "stdout_tail": stdout,
            "stderr_tail": stderr,
            "artifacts": [
                str(path.relative_to(output)) for path in sorted(set(case_dir.iterdir()) - before)
            ],
        }
    stdout = stdout_path.read_text(encoding="utf-8", errors="replace")[-4_000:]
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace")[-4_000:]
    if timed_out:
        wall_duration_ms = round((time.monotonic() - started) * 1000)
        timeout_result = {
            "id": case.id,
            "categories": list(case.categories),
            "kind": case.kind,
            "source": case.source(),
            "notes": case.notes,
            **smoke_metadata,
            "command": command,
            "exit_code": None,
            "wall_duration_ms": wall_duration_ms,
            "runtime_error": f"case exceeded {case_timeout_ms}ms deadline",
            "stdout_tail": stdout,
            "stderr_tail": stderr,
            "artifacts": [
                str(path.relative_to(output)) for path in sorted(set(case_dir.iterdir()) - before)
            ],
        }
        print(
            f"[{index:>2}/{total}] {case.id}: runtime error (case timeout)",
            flush=True,
        )
        return timeout_result
    wall_duration_ms = round((time.monotonic() - started) * 1000)
    report_path = case_dir / "report.json"
    summary_path = case_dir / "agent_summary.json"
    result: dict[str, Any] = {
        "id": case.id,
        "categories": list(case.categories),
        "kind": case.kind,
        "source": case.source(),
        "notes": case.notes,
        **smoke_metadata,
        "command": command,
        "exit_code": returncode,
        "wall_duration_ms": wall_duration_ms,
        "report": str(report_path.relative_to(output)),
        "agent_summary": str(summary_path.relative_to(output)),
        "artifacts": [
            str(path.relative_to(output)) for path in sorted(set(case_dir.iterdir()) - before)
        ],
        "stdout_tail": stdout,
        "stderr_tail": stderr,
    }
    if returncode not in {0, 1}:
        result["runtime_error"] = stderr or stdout or "CLI returned an unexpected exit code"
        print(f"[{index:>2}/{total}] {case.id}: runtime error ({returncode})", flush=True)
        return result
    try:
        report = _json_file(report_path)
        agent_summary = _json_file(summary_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        result["runtime_error"] = f"missing or invalid report: {exc}"
        print(f"[{index:>2}/{total}] {case.id}: invalid evidence", flush=True)
        return result
    counts = report.get("counts", {})
    summary = agent_summary.get("summary", {})
    result.update(
        {
            "status": report.get("status"),
            "report_duration_ms": report.get("duration_ms"),
            "issue_count": len(report.get("issues", [])),
            "failed_item_count": len(agent_summary.get("failed_items", [])),
            "counts": counts,
            "finding_codes": sorted(
                {
                    str(item.get("dimension_id"))
                    for item in agent_summary.get("failed_items", [])
                    if isinstance(item, Mapping)
                }
            ),
            "agent_summary_counts": summary,
        }
    )
    print(
        f"[{index:>2}/{total}] {case.id}: {result['status']}, "
        f"{result['issue_count']} issue(s), {wall_duration_ms}ms",
        flush=True,
    )
    return result


def _nearest_rank(values: Sequence[int], percentile: int) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, (percentile * len(ordered) + 99) // 100 - 1)
    return ordered[min(index, len(ordered) - 1)]


def _metrics(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    successful = [item for item in results if not item.get("runtime_error")]
    durations = [
        int(item["wall_duration_ms"])
        for item in successful
        if isinstance(item.get("wall_duration_ms"), int)
    ]
    statuses = Counter(str(item.get("status")) for item in successful)
    finding_codes = Counter(
        code
        for item in successful
        for code in item.get("finding_codes", [])
        if isinstance(code, str)
    )
    return {
        "cases": len(results),
        "successful_audits": len(successful),
        "runtime_errors": len(results) - len(successful),
        "statuses": dict(sorted(statuses.items())),
        "total_issues": sum(int(item.get("issue_count", 0)) for item in successful),
        "runtime_ms": {
            "p50": _nearest_rank(durations, 50),
            "p95": _nearest_rank(durations, 95),
            "max": max(durations) if durations else None,
        },
        "finding_codes": dict(sorted(finding_codes.items())),
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_smoke_config(case: DogfoodCase, case_dir: Path) -> None:
    steps: list[dict[str, str]] = []
    for step in case.smoke_flow:
        payload = {"action": step.action}
        for key in ("selector", "value", "key", "pattern"):
            value = getattr(step, key)
            if value:
                payload[key] = value
        steps.append(payload)
    _write_json(case_dir / DOGFOOD_CONFIG_NAME, {"smoke_flow": steps})


def _render_markdown(manifest: DogfoodManifest, results: Sequence[Mapping[str, Any]]) -> str:
    metrics = _metrics(results)
    runtime = metrics["runtime_ms"]
    lines = [
        f"# Dogfood run: {manifest.name}",
        "",
        f"- Cases: {metrics['cases']}",
        f"- Successful audits: {metrics['successful_audits']}",
        f"- Runtime errors: {metrics['runtime_errors']}",
        f"- Statuses: {json.dumps(metrics['statuses'], ensure_ascii=False)}",
        f"- Total issues: {metrics['total_issues']}",
        f"- P50/P95/max: {runtime['p50']}/{runtime['p95']}/{runtime['max']} ms",
        "",
        "| Case | Smoke | Categories | Result | Issues | Wall time | Finding codes |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for item in results:
        result = "runtime error" if item.get("runtime_error") else str(item.get("status"))
        codes = ", ".join(item.get("finding_codes", [])) or "-"
        smoke = str(item.get("smoke_mode", "disabled"))
        if item.get("smoke_flow_steps"):
            smoke = f"{smoke} ({item['smoke_flow_steps']} steps)"
        lines.append(
            f"| `{item['id']}` | {smoke} | {', '.join(item.get('categories', []))} | {result} | "
            f"{item.get('issue_count', '-')} | {item.get('wall_duration_ms', '-')} ms | {codes} |"
        )
    lines.extend(
        [
            "",
            "Generated evidence is intentionally ignored by Git. Human TP/FP/FN and repair",
            "outcomes belong in a dated report under `docs/`.",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="dogfood/cases.json")
    parser.add_argument("--ego-root", default=os.environ.get("EGO_ROOT", ""))
    parser.add_argument(
        "--project-space",
        default=os.environ.get("EGO_PROJECT_SPACE", ""),
    )
    parser.add_argument("--out", help="result directory; defaults to a timestamped directory")
    parser.add_argument("--browser-channel", default="")
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--case-timeout-ms", type=int, default=180_000)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.ego_root or not args.project_space:
        print(
            "dogfood: provide --ego-root/--project-space or set EGO_ROOT/EGO_PROJECT_SPACE",
            file=sys.stderr,
        )
        return 2
    if args.case_timeout_ms < 1:
        print("dogfood: --case-timeout-ms must be positive", file=sys.stderr)
        return 2
    variables = {
        "EGO_ROOT": Path(args.ego_root),
        "EGO_PROJECT_SPACE": Path(args.project_space),
    }
    try:
        manifest = load_manifest(args.manifest, variables)
    except DogfoodConfigError as exc:
        print(f"dogfood: {exc}", file=sys.stderr)
        return 2
    selected = {case.id for case in manifest.cases} if not args.case else set(args.case)
    unknown = sorted(selected - {case.id for case in manifest.cases})
    if unknown:
        print(f"dogfood: unknown case id(s): {', '.join(unknown)}", file=sys.stderr)
        return 2
    cases = tuple(case for case in manifest.cases if case.id in selected)
    if not cases:
        print("dogfood: no cases selected", file=sys.stderr)
        return 2
    missing = [
        case.id
        for case in cases
        if case.kind == "local" and not (Path(case.directory) / case.file).is_file()
    ]
    if missing:
        print(f"dogfood: local source missing for: {', '.join(missing)}", file=sys.stderr)
        return 2

    generated_at = datetime.now(timezone.utc)
    output = (
        Path(args.out)
        if args.out
        else Path("dogfood-results") / generated_at.strftime("%Y%m%dT%H%M%SZ")
    ).resolve()
    output.mkdir(parents=True, exist_ok=True)
    results = [
        _run_case(
            index,
            len(cases),
            case,
            output,
            args.browser_channel,
            args.case_timeout_ms,
        )
        for index, case in enumerate(cases, start=1)
    ]
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "generated_at": generated_at.isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "ego_webqa_version": __version__,
            "browser_channel": args.browser_channel or "playwright-default",
        },
        "manifest": {
            "path": str(manifest.path),
            "sha256": manifest.sha256,
            "name": manifest.name,
            "selected_cases": len(cases),
        },
        "metrics": _metrics(results),
        "cases": results,
    }
    _write_json(output / "result.json", payload)
    (output / "summary.md").write_text(
        _render_markdown(manifest, results),
        encoding="utf-8",
    )
    metrics = payload["metrics"]
    print(
        f"dogfood: {metrics['successful_audits']}/{metrics['cases']} audited, "
        f"{metrics['runtime_errors']} runtime error(s), "
        f"P50={metrics['runtime_ms']['p50']}ms, P95={metrics['runtime_ms']['p95']}ms"
    )
    print(f"dogfood: evidence {output / 'result.json'}")
    return 1 if metrics["runtime_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
