"""JSON, JUnit XML, and SARIF writers."""

from __future__ import annotations

import json
import shlex
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any

from .dimensions import dimension_for
from .feedback import build_feedback_bundle
from .models import AuditReport, Issue

SCOPE_STATEMENT = (
    "本报告仅覆盖多终端几何与基础体验的确定性粗检；"
    "业务主路径、跨浏览器兼容、安全合规需另行验证。"
)


def write_reports(report: AuditReport, output_dir: str | Path) -> dict[str, str]:
    """Write all machine-readable artifacts and return their locations."""

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    json_path = out / "report.json"
    agent_summary_path = out / "agent_summary.json"
    feedback_path = out / "feedback_bundle.json"
    junit_path = out / "junit.xml"
    sarif_path = out / "report.sarif"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    agent_summary_path.write_text(
        json.dumps(build_agent_summary(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    feedback_path.write_text(
        json.dumps(build_feedback_bundle(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    junit_path.write_text(to_junit(report), encoding="utf-8")
    sarif_path.write_text(
        json.dumps(to_sarif(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "json": str(json_path),
        "agent_summary": str(agent_summary_path),
        "feedback_bundle": str(feedback_path),
        "junit": str(junit_path),
        "sarif": str(sarif_path),
    }


def build_agent_summary(report: AuditReport) -> dict[str, Any]:
    """Aggregate issues into root causes that an agent can repair and rerun."""

    grouped: dict[str, list[Issue]] = defaultdict(list)
    for issue in report.issues:
        dimension_for(issue.code)
        grouped[issue.code].append(issue)

    viewport_dimensions = {
        str(row.get("viewport", {}).get("name") or ""): row.get("viewport", {})
        for row in report.viewports
    }
    failed_items = [
        _agent_failure(
            code,
            issues,
            target=report.target,
            viewport_dimensions=viewport_dimensions,
            settings=report.settings,
            smoke_enabled=(
                report.smoke.get("enabled")
                if isinstance(report.smoke.get("enabled"), bool)
                else None
            ),
        )
        for code, issues in grouped.items()
    ]
    failed_items.sort(
        key=lambda item: (
            item["severity"] != "block",
            str(item["dimension_id"]),
        )
    )
    block_count = sum(issue.severity == "error" for issue in report.issues)
    warn_count = sum(issue.severity == "warning" for issue in report.issues)
    governance = dict(report.governance)
    active_overrides = governance.get("active_overrides")
    expired_overrides = governance.get("expired_overrides")
    if not isinstance(active_overrides, list):
        active_overrides = []
    if not isinstance(expired_overrides, list):
        expired_overrides = []
    downgraded_blocks = sum(
        bool(issue.override.get("downgraded"))
        for issue in report.issues
        if issue.severity_source == "override"
    )
    return {
        "schema_version": "1.0",
        "tool": "ego-webqa",
        "target": report.target,
        "status": report.status,
        "failed_items": failed_items,
        "summary": {
            "total_block": block_count,
            "total_warn": warn_count,
            "unique_root_causes": len(failed_items),
            "affected_viewports": len(
                {issue.viewport for issue in report.issues if issue.viewport}
            ),
            "duration_ms": report.duration_ms,
            "overridden_dimensions": len(active_overrides),
            "downgraded_blocks": downgraded_blocks,
            "expired_overrides": len(expired_overrides),
        },
        "governance": governance,
        "scope_statement": SCOPE_STATEMENT,
    }


def _agent_failure(
    code: str,
    issues: list[Issue],
    *,
    target: str,
    viewport_dimensions: dict[str, dict[str, Any]],
    settings: dict[str, Any],
    smoke_enabled: bool | None,
) -> dict[str, Any]:
    dimension = dimension_for(code)
    severities = {issue.severity for issue in issues}
    severity = "block" if "error" in severities else "warn"
    viewport_names = sorted({issue.viewport for issue in issues if issue.viewport})
    viewport_specs = [
        _viewport_spec(name, viewport_dimensions.get(name, {})) for name in viewport_names
    ]
    triggers = [
        f"{name} ({viewport_dimensions.get(name, {}).get('width', '?')}x"
        f"{viewport_dimensions.get(name, {}).get('height', '?')})"
        for name in viewport_names
    ]
    selectors = _collect_strings(
        [issue.evidence for issue in issues],
        {"selector", "selectors"},
    )
    text_snippets = _collect_strings(
        [issue.evidence for issue in issues],
        {"text", "textSnippet", "label", "content"},
    )
    messages = list(dict.fromkeys(issue.message for issue in issues))
    problem = messages[0]
    if len(messages) > 1:
        problem = f"{problem} (+{len(messages) - 1} related finding(s))"
    hint = next((issue.hint for issue in issues if issue.hint), "")
    command = _reproduction_command(
        target,
        viewport_specs,
        settings=settings,
        smoke_enabled=smoke_enabled,
    )
    evidence_by_viewport: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for issue in issues:
        evidence_by_viewport[issue.viewport or "global"].append(dict(issue.evidence))
    override = next(
        (dict(issue.override) for issue in issues if issue.severity_source == "override"),
        {},
    )
    return {
        "dimension_id": dimension.id,
        "dimension_version": dimension.version,
        "detector": dimension.detector,
        "default_severity": dimension.default_severity,
        "severity": severity,
        "severity_source": "override" if override else "default",
        "override": override,
        "selector": selectors[0] if selectors else "html",
        "selectors": selectors,
        "text_snippet": text_snippets[0] if text_snippets else "",
        "trigger": "; ".join(triggers) if triggers else "global",
        "triggers": triggers,
        "problem": problem,
        "problems": messages,
        "suggestion": hint,
        "reproduce": shlex.join(command),
        "occurrences": len(issues),
        "evidence": dict(issues[0].evidence),
        "evidence_by_viewport": dict(evidence_by_viewport),
    }


def _reproduction_command(
    target: str,
    viewport_specs: list[str],
    *,
    settings: dict[str, Any],
    smoke_enabled: bool | None,
) -> list[str]:
    source = settings.get("source")
    if isinstance(source, dict) and source.get("kind") == "directory":
        directory = source.get("directory")
        command = ["ego-webqa", "--dir", str(directory or "")]
        entry_file = source.get("file")
        if isinstance(entry_file, str) and entry_file:
            command.extend(["--file", entry_file])
    else:
        command = ["ego-webqa", target]

    config_path = source.get("config") if isinstance(source, dict) else None
    if isinstance(config_path, str) and config_path:
        command.extend(["--config", config_path])
    profile = settings.get("profile")
    if isinstance(profile, str) and profile != "baseline":
        command.extend(["--profile", profile])
    if viewport_specs:
        command.extend(["--viewports", ",".join(viewport_specs)])
    if settings.get("timeout_ms") not in (None, 15_000):
        command.extend(["--timeout-ms", str(settings["timeout_ms"])])
    if settings.get("ready_selector"):
        command.extend(["--ready-selector", str(settings["ready_selector"])])
    if settings.get("wait_for_network_idle"):
        command.append("--wait-for-network-idle")
    for value in settings.get("ignore_selectors", []):
        command.extend(["--ignore-selector", str(value)])
    for value in settings.get("ignore_console_patterns", []):
        command.extend(["--ignore-console-pattern", str(value)])
    for value in settings.get("ignore_request_patterns", []):
        command.extend(["--ignore-request-pattern", str(value)])
    if settings.get("smoke_selector"):
        command.extend(["--smoke-selector", str(settings["smoke_selector"])])
    if settings.get("smoke_success_selector"):
        command.extend(["--smoke-success-selector", str(settings["smoke_success_selector"])])
    if settings.get("smoke_success_url_pattern"):
        command.extend(["--smoke-success-url-pattern", str(settings["smoke_success_url_pattern"])])
    if settings.get("smoke_scope") not in (None, "first"):
        command.extend(["--smoke-scope", str(settings["smoke_scope"])])
    if settings.get("smoke_settle_ms") not in (None, 800):
        command.extend(["--smoke-settle-ms", str(settings["smoke_settle_ms"])])
    if settings.get("smoke_require_assertion"):
        command.append("--smoke-require-assertion")
    if settings.get("smoke_mode") == "live":
        command.extend(["--smoke-mode", "live"])
    if settings.get("browser_engine") not in (None, "chromium"):
        command.extend(["--browser-engine", str(settings["browser_engine"])])
    if settings.get("browser_channel"):
        command.extend(["--browser-channel", str(settings["browser_channel"])])
    if settings.get("fail_on_warn"):
        command.append("--fail-on-warn")
    if smoke_enabled is False:
        command.append("--no-smoke")
    command.append("--json")
    return command


def _viewport_spec(name: str, viewport: dict[str, Any]) -> str:
    width = viewport.get("width")
    height = viewport.get("height")
    if isinstance(width, int) and isinstance(height, int):
        spec = f"{width}x{height}:{name}"
        text_scale = viewport.get("text_scale")
        if isinstance(text_scale, (int, float)) and text_scale != 1.0:
            spec += f"@{float(text_scale):g}"
        safe_area_bottom_px = viewport.get("safe_area_bottom_px")
        if isinstance(safe_area_bottom_px, int) and safe_area_bottom_px:
            spec += f"~{safe_area_bottom_px}"
        return spec
    return name


def _collect_strings(values: list[Any], keys: set[str]) -> list[str]:
    found: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in keys:
                    if isinstance(item, str) and item:
                        found.append(item)
                    elif isinstance(item, list):
                        found.extend(
                            str(entry) for entry in item if isinstance(entry, str) and entry
                        )
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(values)
    return list(dict.fromkeys(found))[:10]


def to_junit(report: AuditReport) -> str:
    suite = ET.Element(
        "testsuite",
        {
            "name": "ego-webqa",
            "tests": str(max(1, len(report.issues))),
            "failures": str(sum(issue.severity == "error" for issue in report.issues)),
            "skipped": "0",
            "time": f"{report.duration_ms / 1000:.3f}",
        },
    )
    if not report.issues:
        ET.SubElement(
            suite,
            "testcase",
            {"classname": "ego-webqa", "name": "delivery gate", "time": "0.000"},
        )
    for issue in report.issues:
        case = ET.SubElement(
            suite,
            "testcase",
            {
                "classname": f"ego-webqa.{issue.code}",
                "name": f"{issue.viewport or 'global'}: {issue.code}",
                "time": "0.000",
            },
        )
        if issue.severity == "error":
            failure = ET.SubElement(case, "failure", {"message": issue.message})
            failure.text = issue.hint or issue.message
        else:
            ET.SubElement(case, "system-out").text = issue.message
    return ET.tostring(suite, encoding="unicode", xml_declaration=True)


def to_sarif(report: AuditReport) -> dict[str, Any]:
    rules: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    for issue in report.issues:
        rules.setdefault(
            issue.code,
            {
                "id": issue.code,
                "name": issue.code,
                "shortDescription": {"text": issue.code.replace("_", " ")},
                "help": {"text": issue.hint or "Fix the reported delivery issue."},
            },
        )
        results.append(
            {
                "ruleId": issue.code,
                "level": "error" if issue.severity == "error" else "warning",
                "message": {"text": issue.message},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": report.target},
                        }
                    }
                ],
                "properties": {
                    "viewport": issue.viewport,
                    "evidence": issue.evidence,
                    "severitySource": issue.severity_source,
                    "override": issue.override,
                },
            }
        )
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "ego-webqa",
                        "informationUri": "https://github.com/ROY32172310/qa",
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
                "properties": {
                    "status": report.status,
                    "durationMs": report.duration_ms,
                },
            }
        ],
    }
