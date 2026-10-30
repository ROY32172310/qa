"""Baseline comparison for deterministic audit reports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from .dimensions import dimension_for

GateMode = Literal["none", "new"]
ChangeType = Literal["new", "persistent", "changed", "resolved"]


class DeltaCompatibilityError(ValueError):
    """Two reports do not describe a comparable audit configuration."""


def compare_reports(
    baseline: dict[str, Any],
    current: dict[str, Any],
    *,
    gate: GateMode = "new",
    fail_on_warn: bool = False,
    allow_target_change: bool = False,
    allow_configuration_change: bool = False,
) -> dict[str, Any]:
    """Compare stable root-cause fingerprints and return a machine-readable delta."""

    _validate_report(baseline, "baseline")
    _validate_report(current, "current")
    compatibility = _compatibility(
        baseline,
        current,
        allow_target_change=allow_target_change,
        allow_configuration_change=allow_configuration_change,
    )
    before = _aggregate_report(baseline)
    after = _aggregate_report(current)

    changes: list[dict[str, Any]] = []
    for fingerprint in sorted(set(before) | set(after)):
        old = before.get(fingerprint)
        new = after.get(fingerprint)
        if old is None and new is not None:
            changes.append(_change("new", None, new))
        elif old is not None and new is None:
            changes.append(_change("resolved", old, None))
        elif old is not None and new is not None:
            change_type: ChangeType = "changed" if _material_change(old, new) else "persistent"
            changes.append(_change(change_type, old, new))

    changes.sort(
        key=lambda item: (
            {"new": 0, "changed": 1, "persistent": 2, "resolved": 3}[item["change_type"]],
            item["dimension_id"],
            item["fingerprint"],
        )
    )
    counts = {
        change_type: sum(item["change_type"] == change_type for item in changes)
        for change_type in ("new", "persistent", "changed", "resolved")
    }
    gate_failed = gate == "new" and any(item["gate_failed"] for item in changes)
    if gate == "new" and fail_on_warn:
        gate_failed = gate_failed or any(
            item["change_type"] in {"new", "changed"} and item["warning_count_after"] > 0
            for item in changes
        )
    return {
        "schema_version": "1.0",
        "tool": "ego-webqa",
        "status": "fail" if gate_failed else "pass",
        "gate": {"mode": gate, "failed": gate_failed},
        "compatibility": compatibility,
        "baseline": _report_identity(baseline),
        "current": _report_identity(current),
        "summary": {
            **counts,
            "total_changes": len(changes),
            "blocking_regressions": sum(
                item["change_type"] in {"new", "changed"} and item["gate_failed"]
                for item in changes
            ),
        },
        "changes": changes,
    }


def load_report(path: str | Path) -> dict[str, Any]:
    """Load a report object from JSON with actionable errors."""

    report_path = Path(path)
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeltaCompatibilityError(f"cannot load {report_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DeltaCompatibilityError(f"{report_path} must contain a JSON object")
    return payload


def write_delta(delta: dict[str, Any], path: str | Path) -> Path:
    """Write a stable JSON delta and return its path."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(delta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output


def _validate_report(report: dict[str, Any], label: str) -> None:
    if report.get("schema_version") != "1.0":
        raise DeltaCompatibilityError(f"{label} report schema_version must be '1.0'")
    issues = report.get("issues")
    if not isinstance(issues, list):
        raise DeltaCompatibilityError(f"{label} report issues must be a list")
    for issue in issues:
        if not isinstance(issue, dict):
            raise DeltaCompatibilityError(f"{label} report issues must be objects")
        code = issue.get("code")
        severity = issue.get("severity")
        if not isinstance(code, str) or not code:
            raise DeltaCompatibilityError(f"{label} report issue has no dimension code")
        dimension_for(code)
        if severity not in {"error", "warning"}:
            raise DeltaCompatibilityError(f"{label} report issue {code!r} has invalid severity")


def _aggregate_report(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for issue in report["issues"]:
        assert isinstance(issue, dict)
        fingerprint, selectors = _issue_fingerprint(issue)
        group = grouped.setdefault(
            fingerprint,
            {
                "fingerprint": fingerprint,
                "dimension_id": str(issue["code"]),
                "dimension_version": dimension_for(str(issue["code"])).version,
                "selectors": set(),
                "viewports": set(),
                "problems": set(),
                "occurrences": 0,
                "block_count": 0,
                "warning_count": 0,
            },
        )
        group["selectors"].update(selectors)
        viewport = issue.get("viewport")
        if isinstance(viewport, str) and viewport:
            group["viewports"].add(viewport)
        message = issue.get("message")
        if isinstance(message, str) and message:
            group["problems"].add(message)
        group["occurrences"] += 1
        if issue["severity"] == "error":
            group["block_count"] += 1
        else:
            group["warning_count"] += 1
    return grouped


def _issue_fingerprint(issue: dict[str, Any]) -> tuple[str, list[str]]:
    code = str(issue["code"])
    evidence = issue.get("evidence")
    evidence_values = [evidence] if isinstance(evidence, dict) else []
    selectors = _collect_selectors(evidence_values)
    marker_keys = {
        "errors",
        "failures",
        "failure_details",
        "step",
        "assertions",
    }
    if not selectors:
        marker_keys.update(
            {
                "controls",
                "elements",
                "ids",
                "images",
                "jumps",
                "label",
                "media",
                "name",
                "samples",
                "shifts",
                "src",
            }
        )
    markers = _collect_markers(evidence_values, marker_keys)
    identity = {
        "dimension_id": code,
        "selectors": sorted(selectors),
        "markers": sorted(markers),
    }
    canonical = json.dumps(identity, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), sorted(selectors)


def _collect_selectors(values: list[Any]) -> list[str]:
    found: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"selector", "successSelector"} and isinstance(item, str):
                    if item:
                        found.append(item)
                elif key == "selectors" and isinstance(item, list):
                    found.extend(entry for entry in item if isinstance(entry, str) and entry)
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(values)
    return list(dict.fromkeys(found))


def _collect_markers(values: list[Any], keys: set[str]) -> list[str]:
    found: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in keys:
                    found.extend(_stable_marker_values(key, item))
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(values)
    return list(dict.fromkeys(found))


def _stable_marker_values(key: str, value: Any) -> list[str]:
    if isinstance(value, str):
        return [f"{key}:{_normalize_text(value)}"]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [f"{key}:{value}"]
    if isinstance(value, list):
        markers: list[str] = []
        for item in value:
            markers.extend(_stable_marker_values(key, item))
        return markers
    if not isinstance(value, dict):
        return []
    stable_keys = {
        "action",
        "alt",
        "error",
        "errorText",
        "id",
        "index",
        "kind",
        "label",
        "matched",
        "name",
        "pattern",
        "resourceType",
        "role",
        "selector",
        "src",
        "status",
        "tag",
        "text",
        "type",
        "url",
    }
    payload = {
        nested_key: _normalize_marker(item)
        for nested_key, item in value.items()
        if nested_key in stable_keys and not isinstance(item, (dict, list))
    }
    return [f"{key}:{json.dumps(payload, sort_keys=True, ensure_ascii=False)}"]


def _normalize_marker(value: Any) -> Any:
    if isinstance(value, str):
        return _normalize_url(value) if "://" in value else _normalize_text(value)
    return value


def _normalize_url(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.scheme:
        return value
    netloc = parsed.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _material_change(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return bool(
        before["occurrences"] != after["occurrences"]
        or before["block_count"] != after["block_count"]
        or before["warning_count"] != after["warning_count"]
        or before["viewports"] != after["viewports"]
    )


def _change(
    change_type: ChangeType,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> dict[str, Any]:
    source = after or before
    assert source is not None
    before_block = int(before["block_count"]) if before else 0
    after_block = int(after["block_count"]) if after else 0
    before_viewports = set(before["viewports"]) if before else set()
    after_viewports = set(after["viewports"]) if after else set()
    gate_failed = change_type == "new" and after_block > 0
    if change_type == "changed" and after_block > 0:
        gate_failed = (
            before_block == 0
            or after_block > before_block
            or not after_viewports.issubset(before_viewports)
        )
    problems = sorted(source["problems"])
    selectors = sorted(source["selectors"])
    return {
        "fingerprint": source["fingerprint"],
        "dimension_id": source["dimension_id"],
        "dimension_version_after": after["dimension_version"] if after else "",
        "dimension_version_before": before["dimension_version"] if before else "",
        "change_type": change_type,
        "block_count_before": before_block,
        "block_count_after": after_block,
        "warning_count_before": int(before["warning_count"]) if before else 0,
        "warning_count_after": int(after["warning_count"]) if after else 0,
        "occurrences_before": int(before["occurrences"]) if before else 0,
        "occurrences_after": int(after["occurrences"]) if after else 0,
        "viewports_before": sorted(before_viewports),
        "viewports_after": sorted(after_viewports),
        "selectors": selectors,
        "problem": problems[0] if problems else "",
        "gate_failed": gate_failed,
    }


def _compatibility(
    baseline: dict[str, Any],
    current: dict[str, Any],
    *,
    allow_target_change: bool,
    allow_configuration_change: bool,
) -> dict[str, Any]:
    baseline_source = _source_identity(baseline)
    current_source = _source_identity(current)
    baseline_runtime = _runtime_identity(baseline)
    current_runtime = _runtime_identity(current)
    baseline_config = _configuration_identity(baseline)
    current_config = _configuration_identity(current)
    if not allow_target_change and baseline_source != current_source:
        raise DeltaCompatibilityError(
            "baseline and current reports target different sources; "
            "use --allow-target-change only for an intentional comparison"
        )
    if not allow_configuration_change and baseline_config != current_config:
        raise DeltaCompatibilityError(
            "baseline and current reports use different profiles or viewport matrices; "
            "use --allow-configuration-change only for an intentional comparison"
        )
    if not allow_configuration_change and baseline_runtime != current_runtime:
        raise DeltaCompatibilityError(
            "baseline and current reports use different browser runtimes; "
            "use --allow-configuration-change only for an intentional comparison"
        )
    return {
        "target_matches": baseline_source == current_source,
        "configuration_matches": baseline_config == current_config,
        "runtime_matches": baseline_runtime == current_runtime,
        "target_change_allowed": allow_target_change,
        "configuration_change_allowed": allow_configuration_change,
    }


def _source_identity(report: dict[str, Any]) -> tuple[str, ...]:
    settings = report.get("settings")
    source = settings.get("source") if isinstance(settings, dict) else None
    if isinstance(source, dict) and source.get("kind") == "directory":
        return (
            "directory",
            str(source.get("directory", "")),
            str(source.get("file", "")),
        )
    target = report.get("target")
    return ("target", str(target or ""))


def _configuration_identity(report: dict[str, Any]) -> tuple[Any, ...]:
    settings = report.get("settings")
    settings = settings if isinstance(settings, dict) else {}
    viewports = report.get("viewports")
    signatures: list[tuple[Any, ...]] = []
    if isinstance(viewports, list):
        for row in viewports:
            viewport = row.get("viewport") if isinstance(row, dict) else None
            if isinstance(viewport, dict):
                signatures.append(
                    (
                        int(viewport.get("width") or 0),
                        int(viewport.get("height") or 0),
                        float(viewport.get("text_scale") or 1.0),
                        int(viewport.get("safe_area_bottom_px") or 0),
                        bool(viewport.get("has_touch", False)),
                    )
                )
    return (str(settings.get("profile", "baseline")), tuple(signatures))


def _runtime_identity(report: dict[str, Any]) -> tuple[str, str]:
    runtime = report.get("runtime")
    runtime = runtime if isinstance(runtime, dict) else {}
    return (
        str(runtime.get("browser_engine", "chromium")),
        str(runtime.get("browser_channel", "")),
    )


def _report_identity(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_kind": _source_identity(report)[0],
        "status": str(report.get("status", "")),
        "counts": report.get("counts", {}),
        "duration_ms": int(report.get("duration_ms") or 0),
        "runtime": {
            "browser_engine": _runtime_identity(report)[0],
            "browser_channel": _runtime_identity(report)[1],
        },
    }
