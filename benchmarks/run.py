#!/usr/bin/env python3
"""Run the public ego-webqa benchmark against a local Chromium browser."""

from __future__ import annotations

import argparse
import contextlib
import functools
import http.server
import importlib.metadata
import json
import platform
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parent.parent
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from benchmarks.eval import (  # noqa: E402
    BenchmarkCase,
    BenchmarkConfigError,
    evaluate_cases,
    load_suite,
    render_markdown,
    select_cases,
)
from ego_webqa import __version__  # noqa: E402
from ego_webqa.config import Settings  # noqa: E402
from ego_webqa.engine import AuditRuntimeError, audit  # noqa: E402


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def do_GET(self) -> None:
        if self.path == "/__slow_response__":
            time.sleep(4.0)
            body = (
                b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">'
                b'<rect width="1" height="1" fill="#ddd"/></svg>'
            )
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                self.wfile.write(body)
            return
        super().do_GET()


class BenchmarkServer:
    """Serve fixtures plus bounded synthetic slow responses."""

    def __init__(self, root: Path) -> None:
        handler = functools.partial(_QuietHandler, directory=str(root))
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def url(self, filename: str) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/{filename}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default="benchmarks/suite.json")
    parser.add_argument("--fixtures", help="override the fixture directory")
    parser.add_argument("--out", help="result directory (default: timestamped benchmark-results)")
    parser.add_argument("--case", action="append", default=[], help="run an expanded case id")
    parser.add_argument("--tag", action="append", default=[], help="require a case tag")
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="parallel audits for throughput; values above 1 invalidate latency comparisons",
    )
    parser.add_argument("--browser-channel", help="Chromium channel override")
    parser.add_argument("--allow-mismatch", action="store_true", help="exit 0 on mismatches")
    parser.add_argument("--list", action="store_true", help="list expanded cases and exit")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.jobs < 1 or args.jobs > 8:
        print("benchmark: --jobs must be between 1 and 8", file=sys.stderr)
        return 2
    try:
        suite = load_suite(args.suite, args.fixtures)
        cases = select_cases(suite.cases, ids=args.case, tags=args.tag)
    except BenchmarkConfigError as exc:
        print(f"benchmark: {exc}", file=sys.stderr)
        return 2
    if args.list:
        for case in cases:
            print(f"{case.id}\t{case.profile}\tsmoke={str(case.smoke).lower()}")
        return 0

    prepared: dict[str, Settings] = {}
    try:
        for case in cases:
            updates: dict[str, Any] = {
                "viewports": [case.viewport_value],
                "profile": case.profile,
                **dict(case.settings),
            }
            if args.browser_channel:
                updates["browser_channel"] = args.browser_channel
            prepared[case.id] = Settings.from_mapping(updates)
    except ValueError as exc:
        print(f"benchmark: invalid case settings: {exc}", file=sys.stderr)
        return 2

    generated_at = datetime.now(timezone.utc)
    output = (
        Path(args.out)
        if args.out
        else Path("benchmark-results") / generated_at.strftime("%Y%m%dT%H%M%SZ")
    ).resolve()
    output.mkdir(parents=True, exist_ok=True)
    fixture_root = (
        Path(args.fixtures).resolve() if args.fixtures else suite.path.parent / "fixtures"
    )
    server = BenchmarkServer(fixture_root)
    started = time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = [
                pool.submit(_run_case, index, len(cases), case, prepared[case.id], server, output)
                for index, case in enumerate(cases, start=1)
            ]
            observations = {
                case.id: future.result() for case, future in zip(cases, futures, strict=True)
            }
    finally:
        server.close()
    wall_ms = round((time.monotonic() - started) * 1000)

    result = evaluate_cases(cases, observations)
    browser_labels = sorted(
        {
            str(issue.get("browser_channel") or "")
            for observation in observations.values()
            for issue in [observation]
            if issue.get("browser_channel")
        }
    )
    environment = _environment(
        suite_sha256=suite.sha256,
        generated_at=generated_at.isoformat(),
        browser=" + ".join(browser_labels) or "unknown",
        jobs=args.jobs,
        wall_ms=wall_ms,
    )
    payload = {
        "schema_version": "1.0",
        "environment": environment,
        "suite": {
            "path": str(suite.path),
            "sha256": suite.sha256,
            "metadata": dict(suite.metadata),
            "selected_case_count": len(cases),
        },
        **result,
    }
    _write_json(output / "result.json", payload)
    (output / "summary.md").write_text(render_markdown(result, environment), encoding="utf-8")
    metrics = result["metrics"]
    failures = result["failures"]
    print(
        f"benchmark: {metrics['exact_matches']}/{metrics['total_cases']} exact, "
        f"blocking FP={metrics['blocking_case_level']['false_positive_rate']:.2%}, "
        f"blocking FN={metrics['blocking_case_level']['false_negative_rate']:.2%}, "
        f"P50={metrics['runtime_ms']['p50']}ms, P95={metrics['runtime_ms']['p95']}ms"
    )
    if failures:
        print(f"benchmark: {len(failures)} mismatch(es)", file=sys.stderr)
        for failure in failures[:20]:
            print(
                f"  {failure['id']}: missing={failure['missing_issue_codes']} "
                f"unexpected={failure['unexpected_issue_codes']} "
                f"error={failure['error']!r}",
                file=sys.stderr,
            )
    print(f"benchmark: evidence {output / 'result.json'}")
    return 0 if args.allow_mismatch or not failures else 1


def _run_case(
    index: int,
    total: int,
    case: BenchmarkCase,
    settings: Settings,
    server: BenchmarkServer,
    output: Path,
) -> dict[str, Any]:
    if case.target.startswith("/"):
        target = server.url(case.target.lstrip("/"))
    else:
        target = case.target or server.url(case.fixture)
    case_dir = output / "cases" / case.id
    case_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    try:
        report = audit(target, settings=settings, output_dir=case_dir, smoke=case.smoke)
        duration_ms = round((time.monotonic() - started) * 1000)
        report_payload = report.to_dict()
        report_path = case_dir / "report.json"
        _write_json(report_path, report_payload)
        observation: dict[str, Any] = {
            "issues": report_payload["issues"],
            "duration_ms": duration_ms,
            "browser_channel": report.runtime.get("browser_channel", ""),
            "artifacts": {
                "report": str(report_path.relative_to(output)),
                "screenshots": report.screenshots,
            },
        }
        print(
            f"[{index:>3}/{total}] {case.id}: " f"{len(report.issues)} finding(s), {duration_ms}ms",
            flush=True,
        )
        return observation
    except (AuditRuntimeError, OSError, ValueError) as exc:
        duration_ms = round((time.monotonic() - started) * 1000)
        observation = {
            "issues": [],
            "duration_ms": duration_ms,
            "browser_channel": "",
            "error": str(exc),
            "artifacts": {"case_directory": str(case_dir.relative_to(output))},
        }
        print(f"[{index:>3}/{total}] {case.id}: runtime error: {exc}", flush=True)
        return observation


def _environment(
    *,
    suite_sha256: str,
    generated_at: str,
    browser: str,
    jobs: int,
    wall_ms: int,
) -> dict[str, Any]:
    return {
        "generated_at": generated_at,
        "tool_version": __version__,
        "git_commit": _git(["rev-parse", "HEAD"]),
        "git_dirty": bool(_git(["status", "--porcelain"])),
        "suite_sha256": suite_sha256,
        "browser": browser,
        "playwright_version": _package_version("playwright"),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "jobs": jobs,
        "execution_profile": "controlled-local",
        "latency_role": "regression" if jobs == 1 else "throughput-only",
        "latency_comparable": jobs == 1,
        "wall_ms": wall_ms,
    }


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return ""


def _git(arguments: Sequence[str]) -> str:
    try:
        return subprocess.run(
            ["git", *arguments],
            cwd=REPOSITORY,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
