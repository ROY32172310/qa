"""Privacy-first report summaries for external feedback."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from . import __version__
from .dimensions import dimension_for


def build_feedback_bundle(
    report: dict[str, Any],
    *,
    include_target: bool = False,
    include_selectors: bool = False,
    include_messages: bool = False,
) -> dict[str, Any]:
    """Build a reviewable bundle without copying raw evidence by default."""

    if not isinstance(report, dict):
        raise ValueError("report must be a JSON object")
    issues = report.get("issues", [])
    if not isinstance(issues, list):
        raise ValueError("report issues must be a list")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for issue in issues:
        if not isinstance(issue, dict):
            raise ValueError("each report issue must be a JSON object")
        code = issue.get("code")
        if not isinstance(code, str) or not code:
            raise ValueError("each report issue must have a code")
        dimension_for(code)
        grouped[code].append(issue)

    viewport_indexes = _viewport_indexes(report.get("viewports"))
    findings = [
        _finding(
            code,
            code_issues,
            viewport_indexes=viewport_indexes,
            include_selectors=include_selectors,
            include_messages=include_messages,
        )
        for code, code_issues in grouped.items()
    ]
    findings.sort(
        key=lambda item: (
            -int(item["block_count"]),
            str(item["dimension_id"]),
        )
    )
    bundle: dict[str, Any] = {
        "bundle_schema_version": "1.0",
        "tool": "ego-webqa",
        "tool_version": __version__,
        "report_schema_version": ("1.0" if report.get("schema_version") == "1.0" else "unknown"),
        "status": _closed_choice(report.get("status"), {"pass", "warn", "fail"}),
        "duration_ms": _integer(report.get("duration_ms")),
        "target_kind": _target_kind(report),
        "counts": {
            "error": sum(issue.get("severity") == "error" for issue in issues),
            "warning": sum(issue.get("severity") == "warning" for issue in issues),
            "root_causes": len(findings),
        },
        "settings": _safe_settings(report.get("settings")),
        "runtime": _safe_runtime(report.get("runtime")),
        "viewports": _safe_viewports(report.get("viewports")),
        "findings": findings,
        "privacy": {
            "target_included": include_target,
            "selectors_included": include_selectors,
            "messages_included": include_messages,
            "excluded_by_default": [
                "target URL and local filesystem paths",
                "custom viewport names",
                "selectors and page text",
                "issue messages, hints, and raw evidence",
                "screenshots",
                "storage state and configuration file contents",
            ],
        },
    }
    if include_target:
        bundle["target"] = str(report.get("target", ""))
    return bundle


def _finding(
    code: str,
    issues: list[dict[str, Any]],
    *,
    viewport_indexes: dict[str, int],
    include_selectors: bool,
    include_messages: bool,
) -> dict[str, Any]:
    dimension = dimension_for(code)
    finding: dict[str, Any] = {
        "dimension_id": dimension.id,
        "dimension_version": dimension.version,
        "detector": dimension.detector,
        "default_severity": dimension.default_severity,
        "block_count": sum(issue.get("severity") == "error" for issue in issues),
        "warning_count": sum(issue.get("severity") == "warning" for issue in issues),
        "occurrences": len(issues),
        "viewport_indexes": sorted(
            {
                viewport_indexes[viewport]
                for issue in issues
                if isinstance((viewport := issue.get("viewport")), str)
                and viewport
                and viewport in viewport_indexes
            }
        ),
    }
    if include_selectors:
        finding["selectors"] = _strings_from_evidence(issues, {"selector", "selectors"})
    if include_messages:
        finding["messages"] = _deduplicated_strings(issues, "message")
        finding["hints"] = _deduplicated_strings(issues, "hint")
        finding["text_snippets"] = _strings_from_evidence(
            issues,
            {"text", "textSnippet", "label", "content"},
        )
    return finding


def _safe_settings(value: Any) -> dict[str, Any]:
    settings = value if isinstance(value, dict) else {}
    source = settings.get("source")
    source_kind = source.get("kind") if isinstance(source, dict) else None
    profile = settings.get("profile")
    browser_engine = settings.get("browser_engine")
    smoke_mode = settings.get("smoke_mode")
    return {
        "profile": _closed_choice(profile, {"baseline", "accessibility"}),
        "browser_engine": _closed_choice(
            browser_engine,
            {"chromium", "firefox", "webkit"},
        ),
        "browser_channel": _safe_browser_channel(settings.get("browser_channel")),
        "fail_on_warn": bool(settings.get("fail_on_warn", False)),
        "wait_for_network_idle": bool(settings.get("wait_for_network_idle", False)),
        "smoke_mode": _closed_choice(smoke_mode, {"safe", "live"}),
        "ready_selector_configured": bool(settings.get("ready_selector")),
        "smoke_configured": bool(settings.get("smoke_selector") or settings.get("smoke_flow")),
        "source_kind": _closed_choice(source_kind, {"url", "directory"}),
    }


def _safe_runtime(value: Any) -> dict[str, Any]:
    runtime = value if isinstance(value, dict) else {}
    engine = runtime.get("browser_engine")
    return {
        "browser_engine": _closed_choice(engine, {"chromium", "firefox", "webkit"}),
        "browser_channel": _safe_browser_channel(runtime.get("browser_channel")),
        "transient_retry_count": _integer(runtime.get("transient_retry_count")),
    }


def _safe_viewports(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    viewports: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, dict) or not isinstance(row.get("viewport"), dict):
            continue
        viewport = row["viewport"]
        viewports.append(
            {
                "index": len(viewports),
                "width": _integer(viewport.get("width")),
                "height": _integer(viewport.get("height")),
                "text_scale": _number(viewport.get("text_scale", 1.0)),
                "safe_area_bottom_px": _integer(viewport.get("safe_area_bottom_px")),
                "has_touch": bool(viewport.get("has_touch", False)),
            }
        )
    return viewports


def _viewport_indexes(value: Any) -> dict[str, int]:
    if not isinstance(value, list):
        return {}
    indexes: dict[str, int] = {}
    for index, row in enumerate(value):
        if not isinstance(row, dict) or not isinstance(row.get("viewport"), dict):
            continue
        name = row["viewport"].get("name")
        if isinstance(name, str) and name:
            indexes[name] = index
    return indexes


def _target_kind(report: dict[str, Any]) -> str:
    settings = report.get("settings")
    source = settings.get("source") if isinstance(settings, dict) else None
    if isinstance(source, dict) and source.get("kind") == "directory":
        return "local"
    target = report.get("target")
    if isinstance(target, str) and (
        target.startswith("file:") or "://127.0.0.1" in target or "://localhost" in target
    ):
        return "local"
    return "remote" if target else "unknown"


def _strings_from_evidence(
    issues: list[dict[str, Any]],
    keys: set[str],
) -> list[str]:
    found: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in keys:
                    if isinstance(item, str) and item:
                        found.append(item)
                    elif isinstance(item, list):
                        found.extend(entry for entry in item if isinstance(entry, str) and entry)
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    for issue in issues:
        visit(issue.get("evidence"))
    return list(dict.fromkeys(found))[:20]


def _deduplicated_strings(issues: list[dict[str, Any]], key: str) -> list[str]:
    values = (issue.get(key) for issue in issues)
    return list(dict.fromkeys(value for value in values if isinstance(value, str) and value))


def _integer(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 1.0


def _closed_choice(value: Any, choices: set[str]) -> str:
    return value if isinstance(value, str) and value in choices else "unknown"


def _safe_browser_channel(value: Any) -> str:
    return _closed_choice(
        value,
        {
            "chrome",
            "chrome-beta",
            "chrome-dev",
            "chrome-canary",
            "msedge",
            "msedge-beta",
            "msedge-dev",
            "msedge-canary",
        },
    )
