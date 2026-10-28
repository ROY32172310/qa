"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .config import (
    Settings,
    Viewport,
    apply_auth_environment,
    load_settings,
)
from .engine import AuditRuntimeError, audit
from .reporting import write_reports
from .server import LocalServer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ego-webqa",
        description="Deterministic delivery QA for AI-generated web pages.",
    )
    parser.add_argument("url", nargs="?", help="page URL")
    parser.add_argument("--dir", help="serve this local directory during the audit")
    parser.add_argument("--file", default="index.html", help="entry file under --dir")
    parser.add_argument("--config", help="JSON configuration file")
    parser.add_argument(
        "--profile",
        choices=("baseline", "accessibility"),
        help="check profile (baseline or baseline plus accessibility checks)",
    )
    parser.add_argument(
        "--viewports",
        help="comma-separated WIDTHxHEIGHT[:NAME] list (default: 390x844,768x1024,1280x800)",
    )
    parser.add_argument("--out", default="webqa-report", help="artifact directory")
    parser.add_argument("--timeout-ms", type=int, help="navigation/action timeout")
    parser.add_argument("--ready-selector", help="wait for this selector before probing")
    parser.add_argument(
        "--wait-for-network-idle",
        action="store_true",
        help="wait up to 3 seconds for network idle before probing",
    )
    parser.add_argument(
        "--ignore-selector",
        action="append",
        default=[],
        help="selector to exclude",
    )
    parser.add_argument(
        "--ignore-console-pattern",
        action="append",
        default=[],
        help="regular expression for known console.error noise",
    )
    parser.add_argument(
        "--ignore-request-pattern",
        action="append",
        default=[],
        help="regular expression for known failed-request noise",
    )
    parser.add_argument("--smoke-selector", help="explicit primary CTA selector")
    parser.add_argument(
        "--smoke-success-selector",
        help="selector that must transition to visible after the CTA click",
    )
    parser.add_argument(
        "--smoke-success-url-pattern",
        help="regular expression the URL must newly match after the CTA click",
    )
    parser.add_argument(
        "--smoke-scope",
        choices=("first", "all"),
        help="run the CTA smoke in the first viewport or every viewport",
    )
    parser.add_argument(
        "--smoke-settle-ms",
        type=int,
        help="time to wait after clicking the CTA before evaluating evidence",
    )
    parser.add_argument(
        "--smoke-require-assertion",
        action="store_true",
        help="require a selector or URL assertion for CTA success",
    )
    parser.add_argument(
        "--storage-state",
        help="Playwright storage-state JSON file for an authenticated preview",
    )
    parser.add_argument(
        "--browser-channel",
        help="Chrome channel, e.g. chrome, chrome-beta, msedge",
    )
    parser.add_argument("--no-smoke", action="store_true", help="skip the primary-CTA click")
    parser.add_argument(
        "--smoke-mode",
        choices=("safe", "live"),
        help="safe blocks smoke-test network requests; live permits real side effects",
    )
    parser.add_argument("--fail-on-warn", action="store_true", help="make warnings exit non-zero")
    parser.add_argument("--json", action="store_true", help="print the complete JSON report")
    parser.add_argument("--version", action="version", version=f"ego-webqa {__version__}")
    return parser


def _settings(args: argparse.Namespace) -> Settings:
    cfg = load_settings(args.config) if args.config else Settings()
    updates: dict[str, object] = {}
    if args.profile is not None:
        updates["profile"] = args.profile
    if args.viewports:
        updates["viewports"] = [Viewport.parse(item) for item in args.viewports.split(",")]
    if args.timeout_ms is not None:
        updates["timeout_ms"] = args.timeout_ms
    if args.ready_selector is not None:
        updates["ready_selector"] = args.ready_selector
    if args.wait_for_network_idle:
        updates["wait_for_network_idle"] = True
    if args.ignore_selector:
        updates["ignore_selectors"] = [*cfg.ignore_selectors, *args.ignore_selector]
    if args.ignore_console_pattern:
        updates["ignore_console_patterns"] = [
            *cfg.ignore_console_patterns,
            *args.ignore_console_pattern,
        ]
    if args.ignore_request_pattern:
        updates["ignore_request_patterns"] = [
            *cfg.ignore_request_patterns,
            *args.ignore_request_pattern,
        ]
    if args.smoke_selector is not None:
        updates["smoke_selector"] = args.smoke_selector
    if args.smoke_success_selector is not None:
        updates["smoke_success_selector"] = args.smoke_success_selector
    if args.smoke_success_url_pattern is not None:
        updates["smoke_success_url_pattern"] = args.smoke_success_url_pattern
    if args.smoke_scope is not None:
        updates["smoke_scope"] = args.smoke_scope
    if args.smoke_settle_ms is not None:
        updates["smoke_settle_ms"] = args.smoke_settle_ms
    if args.smoke_require_assertion:
        updates["smoke_require_assertion"] = True
    if args.storage_state is not None:
        updates["storage_state"] = args.storage_state
    if args.browser_channel is not None:
        updates["browser_channel"] = args.browser_channel
    if args.smoke_mode is not None:
        updates["smoke_mode"] = args.smoke_mode
    if args.fail_on_warn:
        updates["fail_on_warn"] = True
    return apply_auth_environment(Settings.from_mapping(updates, base=cfg))


def _json_text(payload: object, encoding: str) -> str:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    try:
        text.encode(encoding, errors="strict")
    except UnicodeEncodeError:
        return json.dumps(payload, ensure_ascii=True, indent=2)
    return text


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.url and not args.dir:
        print("ego-webqa: provide a URL or --dir", file=sys.stderr)
        return 2
    if args.url and args.dir:
        print("ego-webqa: provide either a URL or --dir, not both", file=sys.stderr)
        return 2
    try:
        cfg = _settings(args)
    except (OSError, ValueError) as exc:
        print(f"ego-webqa: invalid configuration: {exc}", file=sys.stderr)
        return 2

    server: LocalServer | None = None
    target = args.url or ""
    try:
        if args.dir:
            server = LocalServer(args.dir)
            target = server.url(args.file)
        report = audit(
            target,
            settings=cfg,
            output_dir=Path(args.out),
            smoke=not args.no_smoke,
        )
        artifacts = write_reports(report, args.out)
    except (AuditRuntimeError, OSError, ValueError) as exc:
        print(f"ego-webqa: {exc}", file=sys.stderr)
        return 2
    finally:
        if server is not None:
            server.close()

    if args.json:
        print(_json_text(report.to_dict(), sys.stdout.encoding or "utf-8"))
    else:
        icon = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}[report.status]
        counts = report.to_dict()["counts"]
        print(f"[{icon}] {target}")
        print(
            f"{len(report.viewports)} viewport(s), "
            f"{counts['error']} error(s), {counts['warning']} warning(s), "
            f"{report.duration_ms}ms"
        )
        for issue in report.issues:
            prefix = f"[{issue.viewport}] " if issue.viewport else ""
            print(f"  {issue.severity.upper():7} {prefix}{issue.code}: {issue.message}")
            if issue.hint:
                print(f"          hint: {issue.hint}")
        print(f"artifacts: {artifacts['json']}")
    return 0 if report.status in ("pass", "warn") else 1
