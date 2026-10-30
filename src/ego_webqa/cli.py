"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import __version__
from .config import (
    VIEWPORT_PRESET_NAMES,
    Settings,
    Viewport,
    apply_auth_environment,
    load_settings,
)
from .delta import (
    DeltaCompatibilityError,
    compare_reports,
    load_report,
    write_delta,
)
from .dimensions import registry_payload
from .doctor import collect_doctor_report
from .engine import AuditRuntimeError, audit
from .feedback import build_feedback_bundle
from .reporting import write_reports
from .server import LocalServer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ego-webqa",
        description="Deterministic delivery QA for AI-generated web pages.",
        epilog=(
            "Run 'ego-webqa doctor' to verify the installation, "
            "'ego-webqa feedback' to prepare a privacy-safe issue report, or "
            "'ego-webqa mcp' to start the stdio MCP server."
        ),
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
        help=(
            "comma-separated WIDTHxHEIGHT[:NAME][@TEXT_SCALE][~SAFE_BOTTOM_PX] list "
            "(default: 360/390 mobile x 1.0/1.5 text scale x 0/34px bottom safe area)"
        ),
    )
    parser.add_argument(
        "--preset",
        choices=VIEWPORT_PRESET_NAMES,
        help="closed viewport matrix preset: quick (4 variants) or full (8 variants)",
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
        "--smoke-flow-name",
        help="select one named flow from the smoke_flows config object",
    )
    parser.add_argument(
        "--storage-state",
        help="Playwright storage-state JSON file for an authenticated preview",
    )
    parser.add_argument(
        "--browser-engine",
        choices=("chromium", "firefox", "webkit"),
        help=(
            "Playwright browser engine; WebKit approximates Safari but is not "
            "a real Safari device"
        ),
    )
    parser.add_argument(
        "--browser-channel",
        help="Chromium channel, e.g. chrome, chrome-beta, msedge",
    )
    parser.add_argument("--no-smoke", action="store_true", help="skip the primary-CTA click")
    parser.add_argument(
        "--smoke-mode",
        choices=("safe", "live"),
        help="safe blocks smoke-test network requests; live permits real side effects",
    )
    parser.add_argument("--fail-on-warn", action="store_true", help="make warnings exit non-zero")
    parser.add_argument(
        "--baseline-report",
        help="compare this run with an earlier report.json and write delta.json",
    )
    parser.add_argument(
        "--gate",
        choices=("none", "new"),
        help="baseline gate mode (default: new when --baseline-report is provided)",
    )
    parser.add_argument(
        "--allow-target-change",
        action="store_true",
        help="allow baseline comparison across different URLs or local directories",
    )
    parser.add_argument(
        "--allow-configuration-change",
        action="store_true",
        help="allow baseline comparison across profiles, viewports, or browser runtimes",
    )
    parser.add_argument("--json", action="store_true", help="print the complete JSON report")
    parser.add_argument(
        "--list-dimensions",
        action="store_true",
        help="print the closed dimension registry as JSON and exit",
    )
    parser.add_argument("--version", action="version", version=f"ego-webqa {__version__}")
    return parser


def _settings(args: argparse.Namespace) -> Settings:
    cfg = load_settings(args.config) if args.config else Settings()
    updates: dict[str, object] = {}
    if args.profile is not None:
        updates["profile"] = args.profile
    if args.preset and args.viewports:
        raise ValueError("--preset and --viewports cannot be combined")
    if args.preset:
        updates["viewport_preset"] = args.preset
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
    if args.smoke_flow_name is not None:
        updates["smoke_flow_name"] = args.smoke_flow_name
    if args.storage_state is not None:
        updates["storage_state"] = args.storage_state
    if args.browser_engine is not None:
        updates["browser_engine"] = args.browser_engine
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


def _doctor_main(arguments: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="ego-webqa doctor",
        description="Verify the Python, MCP, Playwright, and browser installation.",
    )
    parser.add_argument(
        "--browser-engine",
        choices=("chromium", "firefox", "webkit"),
        default="chromium",
        help="browser engine to verify",
    )
    parser.add_argument(
        "--browser-channel",
        default="",
        help="optional Chromium channel such as chrome or msedge",
    )
    parser.add_argument("--json", action="store_true", help="print JSON diagnostics")
    args = parser.parse_args(list(arguments))
    report = collect_doctor_report(args.browser_engine, args.browser_channel)
    if args.json:
        print(_json_text(report.to_dict(), sys.stdout.encoding or "utf-8"))
    else:
        print(f"ego-webqa doctor: {report.status.upper()}")
        for check in report.checks:
            print(f"  {check.status.upper():4} {check.id}: {check.message}")
            if check.hint:
                print(f"       {check.hint}")
    return 0 if report.status == "ok" else 1


def _feedback_main(arguments: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="ego-webqa feedback",
        description=(
            "Build a privacy-first feedback bundle from report.json. "
            "Review the output before sharing it."
        ),
    )
    parser.add_argument(
        "--report",
        default="webqa-report/report.json",
        help="path to an ego-webqa report.json",
    )
    parser.add_argument("--out", help="output path (default: beside the input report)")
    parser.add_argument(
        "--include-target",
        action="store_true",
        help="include the audited URL or local path",
    )
    parser.add_argument(
        "--include-selectors",
        action="store_true",
        help="include CSS selectors from issue evidence",
    )
    parser.add_argument(
        "--include-messages",
        action="store_true",
        help="include issue messages, hints, and page text snippets",
    )
    parser.add_argument("--json", action="store_true", help="print the bundle to stdout")
    args = parser.parse_args(list(arguments))
    report_path = Path(args.report)
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        bundle = build_feedback_bundle(
            payload,
            include_target=args.include_target,
            include_selectors=args.include_selectors,
            include_messages=args.include_messages,
        )
        output_path = Path(args.out) if args.out else report_path.with_name("feedback_bundle.json")
        if not args.json:
            output_path.write_text(
                _json_text(bundle, "utf-8") + "\n",
                encoding="utf-8",
            )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ego-webqa: cannot build feedback bundle: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(_json_text(bundle, sys.stdout.encoding or "utf-8"))
    else:
        print(f"feedback bundle: {output_path}")
        print("Review it before sharing; omitted fields are listed in privacy.excluded_by_default.")
    return 0


def _delta_main(arguments: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="ego-webqa delta",
        description="Compare two report.json files by stable root-cause fingerprint.",
    )
    parser.add_argument("--baseline", required=True, help="earlier report.json")
    parser.add_argument("--current", required=True, help="current report.json")
    parser.add_argument("--out", help="output path (default: beside the current report)")
    parser.add_argument(
        "--gate",
        choices=("none", "new"),
        default="new",
        help="new fails only for new or expanding blocking root causes",
    )
    parser.add_argument(
        "--fail-on-warn",
        action="store_true",
        help="also fail the gate for new or changed warnings",
    )
    parser.add_argument(
        "--allow-target-change",
        action="store_true",
        help="allow comparison across different URLs or local directories",
    )
    parser.add_argument(
        "--allow-configuration-change",
        action="store_true",
        help="allow comparison across profiles, viewports, or browser runtimes",
    )
    parser.add_argument("--json", action="store_true", help="print the delta JSON")
    args = parser.parse_args(list(arguments))
    try:
        delta = compare_reports(
            load_report(args.baseline),
            load_report(args.current),
            gate=args.gate,
            fail_on_warn=args.fail_on_warn,
            allow_target_change=args.allow_target_change,
            allow_configuration_change=args.allow_configuration_change,
        )
        output_path = Path(args.out) if args.out else Path(args.current).with_name("delta.json")
        if not args.json:
            write_delta(delta, output_path)
    except (DeltaCompatibilityError, ValueError, OSError) as exc:
        print(f"ego-webqa: cannot compare reports: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(_json_text(delta, sys.stdout.encoding or "utf-8"))
    else:
        _print_delta_summary(delta, output_path)
    return 1 if delta["gate"]["failed"] else 0


def _print_delta_summary(delta: dict[str, Any], output_path: Path) -> None:
    summary = delta["summary"]
    assert isinstance(summary, dict)
    gate = delta["gate"]
    assert isinstance(gate, dict)
    status = "FAIL" if gate["failed"] else "PASS"
    print(
        f"[{status}] delta gate={gate['mode']}: "
        f"{summary['new']} new, {summary['changed']} changed, "
        f"{summary['persistent']} persistent, {summary['resolved']} resolved, "
        f"{summary['blocking_regressions']} blocking regression(s)"
    )
    print(f"delta: {output_path}")


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ["doctor"]:
        return _doctor_main(arguments[1:])
    if arguments[:1] == ["feedback"]:
        return _feedback_main(arguments[1:])
    if arguments[:1] == ["delta"]:
        return _delta_main(arguments[1:])
    if arguments[:1] == ["mcp"]:
        if len(arguments) != 1:
            print("ego-webqa: the mcp command does not accept arguments", file=sys.stderr)
            return 2
        from .mcp_server import main as mcp_main

        mcp_main()
        return 0

    args = build_parser().parse_args(arguments)
    if args.list_dimensions:
        print(_json_text(registry_payload(), sys.stdout.encoding or "utf-8"))
        return 0
    if not args.url and not args.dir:
        print("ego-webqa: provide a URL or --dir", file=sys.stderr)
        return 2
    if args.url and args.dir:
        print("ego-webqa: provide either a URL or --dir, not both", file=sys.stderr)
        return 2
    if args.gate and not args.baseline_report:
        print("ego-webqa: --gate requires --baseline-report", file=sys.stderr)
        return 2
    baseline_report: dict[str, Any] | None = None
    if args.baseline_report:
        try:
            baseline_report = load_report(args.baseline_report)
        except DeltaCompatibilityError as exc:
            print(f"ego-webqa: baseline report: {exc}", file=sys.stderr)
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
        source: dict[str, str] = {"kind": "url"}
        if args.dir:
            source = {
                "kind": "directory",
                "directory": str(Path(args.dir).resolve()),
                "file": args.file,
            }
        if args.config:
            source["config"] = str(Path(args.config).resolve())
        report.settings["source"] = source
        artifacts = write_reports(report, args.out)
        delta: dict[str, Any] | None = None
        if baseline_report is not None:
            delta = compare_reports(
                baseline_report,
                report.to_dict(),
                gate=args.gate or "new",
                fail_on_warn=cfg.fail_on_warn,
                allow_target_change=args.allow_target_change,
                allow_configuration_change=args.allow_configuration_change,
            )
            write_delta(delta, Path(args.out) / "delta.json")
    except (AuditRuntimeError, DeltaCompatibilityError, OSError, ValueError) as exc:
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
        if delta is not None:
            _print_delta_summary(delta, Path(args.out) / "delta.json")
    if delta is not None:
        return 1 if delta["gate"]["failed"] else 0
    return 0 if report.status in ("pass", "warn") else 1
