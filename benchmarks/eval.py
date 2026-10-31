"""Schema validation, case expansion, and deterministic benchmark metrics."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from ego_webqa.dimensions import (
    DIMENSIONS,
    PROFILE_NAMES,
    profile_includes_dimension,
)

SUITE_SCHEMA_VERSION = "1.0"
Severity = Literal["error", "warning"]
_CASE_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_CASE_KEYS = {
    "id",
    "fixture",
    "target",
    "variants",
    "expected_issue_codes",
    "expected_clean",
    "expected_severities",
    "forbidden_issue_codes",
    "profile",
    "smoke",
    "settings",
    "tags",
    "rationale",
}
_RESERVED_SETTINGS = {"viewports", "profile", "metadata"}


class BenchmarkConfigError(ValueError):
    """The benchmark manifest is invalid or ambiguous."""


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    id: str
    fixture: str
    target: str
    viewport: str
    viewport_value: str
    expected_issue_codes: tuple[str, ...]
    expected_clean: bool
    expected_severities: Mapping[str, Severity]
    forbidden_issue_codes: tuple[str, ...]
    profile: str
    smoke: bool
    settings: Mapping[str, Any]
    tags: tuple[str, ...]
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "fixture": self.fixture,
            "target": self.target,
            "viewport": self.viewport,
            "viewport_value": self.viewport_value,
            "expected_issue_codes": list(self.expected_issue_codes),
            "expected_clean": self.expected_clean,
            "expected_severities": dict(self.expected_severities),
            "forbidden_issue_codes": list(self.forbidden_issue_codes),
            "profile": self.profile,
            "smoke": self.smoke,
            "settings": dict(self.settings),
            "tags": list(self.tags),
            "rationale": self.rationale,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkSuite:
    path: Path
    sha256: str
    cases: tuple[BenchmarkCase, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


def load_suite(path: str | Path, fixture_root: str | Path | None = None) -> BenchmarkSuite:
    """Load and validate a suite, expanding its viewport variants."""

    suite_path = Path(path).resolve()
    root = (
        Path(fixture_root).resolve() if fixture_root is not None else suite_path.parent / "fixtures"
    )
    try:
        raw_bytes = suite_path.read_bytes()
        raw = json.loads(raw_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkConfigError(f"cannot load benchmark suite {suite_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise BenchmarkConfigError("benchmark suite root must be an object")
    if raw.get("schema_version") != SUITE_SCHEMA_VERSION:
        raise BenchmarkConfigError(
            f"benchmark suite schema_version must be {SUITE_SCHEMA_VERSION!r}"
        )
    viewports = _validate_viewports(raw.get("viewports"))
    defaults = raw.get("defaults", {})
    if not isinstance(defaults, dict):
        raise BenchmarkConfigError("benchmark suite defaults must be an object")
    raw_cases = raw.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise BenchmarkConfigError("benchmark suite must contain at least one case")

    expanded: list[BenchmarkCase] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw_cases):
        if not isinstance(item, dict):
            raise BenchmarkConfigError(f"case #{index + 1} must be an object")
        unknowns = sorted(set(item) - _CASE_KEYS)
        if unknowns:
            raise BenchmarkConfigError(
                f"case #{index + 1} contains unknown key(s): {', '.join(unknowns)}"
            )
        base_id = _required_string(item, "id", f"case #{index + 1}")
        if not _CASE_ID.fullmatch(base_id):
            raise BenchmarkConfigError(f"case id {base_id!r} must use lowercase kebab-case")
        variants = _variant_names(item.get("variants", defaults.get("variants", ["mobile"])))
        missing_viewports = [name for name in variants if name not in viewports]
        if missing_viewports:
            raise BenchmarkConfigError(
                f"case {base_id!r} uses unknown viewport variant(s): "
                f"{', '.join(missing_viewports)}"
            )
        fixture = _optional_string(item, "fixture", "")
        target = _optional_string(item, "target", "")
        if bool(fixture) == bool(target):
            raise BenchmarkConfigError(
                f"case {base_id!r} must define exactly one of fixture or target"
            )
        if fixture and not (root / fixture).is_file():
            raise BenchmarkConfigError(f"case {base_id!r} fixture does not exist: {fixture}")

        expected = _unique_strings(item.get("expected_issue_codes"), "expected_issue_codes")
        forbidden = _unique_strings(item.get("forbidden_issue_codes", []), "forbidden_issue_codes")
        overlap = sorted(set(expected) & set(forbidden))
        if overlap:
            raise BenchmarkConfigError(
                f"case {base_id!r} has codes both expected and forbidden: {', '.join(overlap)}"
            )
        for code in (*expected, *forbidden):
            if code not in DIMENSIONS:
                raise BenchmarkConfigError(
                    f"case {base_id!r} references unregistered dimension {code!r}"
                )

        expected_clean = item.get("expected_clean")
        if type(expected_clean) is not bool:
            raise BenchmarkConfigError(f"case {base_id!r} expected_clean must be a boolean")
        if expected_clean and (expected or forbidden):
            raise BenchmarkConfigError(
                f"case {base_id!r} cannot be expected_clean with issue codes"
            )
        if not expected_clean and not expected:
            raise BenchmarkConfigError(
                f"case {base_id!r} must declare expected_issue_codes unless expected_clean"
            )

        profile = item.get("profile", defaults.get("profile", "baseline"))
        if profile not in PROFILE_NAMES:
            raise BenchmarkConfigError(
                f"case {base_id!r} profile must be one of: {', '.join(PROFILE_NAMES)}"
            )
        for code in expected:
            if not profile_includes_dimension(profile, code):
                raise BenchmarkConfigError(
                    f"case {base_id!r} expects {code!r}, which is not enabled by "
                    f"the {profile!r} profile"
                )

        expected_severities = _expected_severities(item.get("expected_severities", {}), expected)
        default_settings = defaults.get("settings", {})
        case_settings = item.get("settings", {})
        if not isinstance(default_settings, dict):
            raise BenchmarkConfigError("benchmark suite defaults.settings must be an object")
        if not isinstance(case_settings, dict):
            raise BenchmarkConfigError(f"case {base_id!r} settings must be an object")
        settings = {**default_settings, **case_settings}
        reserved = sorted(set(settings) & _RESERVED_SETTINGS)
        if reserved:
            raise BenchmarkConfigError(
                f"case {base_id!r} settings contains reserved key(s): {', '.join(reserved)}"
            )
        smoke = item.get("smoke", defaults.get("smoke", False))
        if type(smoke) is not bool:
            raise BenchmarkConfigError(f"case {base_id!r} smoke must be a boolean")
        tags = _unique_strings(item.get("tags", []), "tags")
        rationale = _required_string(item, "rationale", f"case {base_id!r}")

        for variant in variants:
            case_id = f"{base_id}--{variant}"
            if case_id in seen_ids:
                raise BenchmarkConfigError(f"duplicate expanded case id {case_id!r}")
            seen_ids.add(case_id)
            expanded.append(
                BenchmarkCase(
                    id=case_id,
                    fixture=fixture,
                    target=target,
                    viewport=variant,
                    viewport_value=viewports[variant],
                    expected_issue_codes=expected,
                    expected_clean=expected_clean,
                    expected_severities=expected_severities,
                    forbidden_issue_codes=forbidden,
                    profile=profile,
                    smoke=smoke,
                    settings=dict(settings),
                    tags=tuple((*tags, variant)),
                    rationale=rationale,
                )
            )

    metadata = raw.get("metadata", {})
    if not isinstance(metadata, dict):
        raise BenchmarkConfigError("benchmark suite metadata must be an object")
    return BenchmarkSuite(
        path=suite_path,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        cases=tuple(expanded),
        metadata=dict(metadata),
    )


def select_cases(
    cases: Sequence[BenchmarkCase],
    *,
    ids: Sequence[str] = (),
    tags: Sequence[str] = (),
) -> tuple[BenchmarkCase, ...]:
    """Select explicit IDs and/or cases carrying every requested tag."""

    selected = tuple(cases)
    if ids:
        requested = set(ids)
        selected = tuple(case for case in selected if case.id in requested)
        missing = sorted(requested - {case.id for case in selected})
        if missing:
            raise BenchmarkConfigError(f"unknown case id(s): {', '.join(missing)}")
    for tag in tags:
        selected = tuple(case for case in selected if tag in case.tags)
    if not selected:
        raise BenchmarkConfigError("case selection produced no benchmark cases")
    return selected


def evaluate_cases(
    cases: Sequence[BenchmarkCase],
    observations: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Compare ground truth to observed audit reports without sharing detector logic."""

    results: list[dict[str, Any]] = []
    tp = fp = fn = tn = 0
    block_tp = block_fp = block_fn = block_tn = 0
    clean_any_fp = clean_block_fp = 0
    defect_any_fn = defect_block_fn = 0
    durations: list[int] = []
    dimension_counts = {
        code: {"expected_cases": 0, "observed_cases": 0, "tp": 0, "fp": 0, "fn": 0, "tn": 0}
        for code in sorted(DIMENSIONS)
    }

    for case in cases:
        observation = observations.get(case.id, {})
        raw_issues = observation.get("issues", [])
        issues = [issue for issue in raw_issues if isinstance(issue, Mapping)]
        observed_severity: dict[str, Severity] = {}
        for issue in issues:
            code = str(issue.get("code") or "")
            severity = str(issue.get("severity") or "")
            if code not in DIMENSIONS or severity not in {"error", "warning"}:
                continue
            if severity == "error" or code not in observed_severity:
                observed_severity[code] = severity  # type: ignore[assignment]
        observed_codes = set(observed_severity)
        expected_codes = set(case.expected_issue_codes)
        unexpected = sorted(observed_codes - expected_codes)
        missing = sorted(expected_codes - observed_codes)
        forbidden_hits = sorted(observed_codes & set(case.forbidden_issue_codes))
        severity_mismatches = sorted(
            code
            for code in expected_codes
            if code in observed_severity
            and observed_severity[code] != _expected_severity(case, code)
        )
        error = str(observation.get("error") or "")
        exact = not error and not unexpected and not missing and not severity_mismatches

        expected_block = {
            code for code in expected_codes if _expected_severity(case, code) == "error"
        }
        observed_block = {
            code for code, severity in observed_severity.items() if severity == "error"
        }
        if expected_codes and observed_codes:
            tp += 1
        elif case.expected_clean and observed_codes:
            fp += 1
        elif expected_codes:
            fn += 1
        elif not error:
            tn += 1
        else:
            fp += 1
        if expected_block and observed_block:
            block_tp += 1
        elif not expected_block and observed_block:
            block_fp += 1
        elif expected_block:
            block_fn += 1
        elif not error:
            block_tn += 1
        else:
            block_fp += 1
        if case.expected_clean and observed_codes:
            clean_any_fp += 1
        if case.expected_clean and observed_block:
            clean_block_fp += 1
        if expected_codes and not observed_codes:
            defect_any_fn += 1
        if expected_block and not observed_block:
            defect_block_fn += 1

        for code, counts in dimension_counts.items():
            expected = code in expected_codes
            observed = code in observed_codes
            counts["expected_cases"] += int(expected)
            counts["observed_cases"] += int(observed)
            if expected and observed:
                key = "tp"
            elif observed:
                key = "fp"
            elif expected:
                key = "fn"
            else:
                key = "tn"
            counts[key] += 1

        duration = observation.get("duration_ms")
        if type(duration) is int and duration >= 0:
            durations.append(duration)
        results.append(
            {
                "id": case.id,
                "viewport": case.viewport,
                "fixture": case.fixture,
                "target": case.target,
                "profile": case.profile,
                "smoke": case.smoke,
                "tags": list(case.tags),
                "rationale": case.rationale,
                "expected_issue_codes": sorted(expected_codes),
                "expected_clean": case.expected_clean,
                "expected_severities": dict(case.expected_severities),
                "observed_issue_codes": sorted(observed_codes),
                "observed_severities": observed_severity,
                "missing_issue_codes": missing,
                "unexpected_issue_codes": unexpected,
                "forbidden_hits": forbidden_hits,
                "severity_mismatches": severity_mismatches,
                "exact_match": exact,
                "error": error,
                "duration_ms": duration,
                "issues": issues,
                "artifacts": observation.get("artifacts", {}),
            }
        )

    total = len(cases)
    clean_cases = sum(case.expected_clean for case in cases)
    defect_cases = total - clean_cases
    expected_block_cases = sum(
        any(_expected_severity(case, code) == "error" for code in case.expected_issue_codes)
        for case in cases
    )
    metrics = {
        "total_cases": total,
        "exact_matches": sum(result["exact_match"] for result in results),
        "exact_match_rate": _ratio(sum(result["exact_match"] for result in results), total),
        "clean_cases": clean_cases,
        "defect_cases": defect_cases,
        "case_level": {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision": _ratio(tp, tp + fp),
            "recall": _ratio(tp, tp + fn),
            "f1": _f1(tp, fp, fn),
            "accuracy": _ratio(tp + tn, total),
            "defect_false_negative_rate": _ratio(defect_any_fn, defect_cases),
            "clean_any_finding_false_positive_rate": _ratio(clean_any_fp, clean_cases),
        },
        "blocking_case_level": {
            "tp": block_tp,
            "fp": block_fp,
            "fn": block_fn,
            "tn": block_tn,
            "precision": _ratio(block_tp, block_tp + block_fp),
            "recall": _ratio(block_tp, block_tp + block_fn),
            "f1": _f1(block_tp, block_fp, block_fn),
            "false_positive_rate": _ratio(block_fp, block_fp + block_tn),
            "false_negative_rate": _ratio(block_fn, block_fn + block_tp),
            "expected_block_cases": expected_block_cases,
        },
        "clean_controls": {
            "clean_blocking_false_positives": clean_block_fp,
            "clean_blocking_false_positive_rate": _ratio(clean_block_fp, clean_cases),
        },
        "runtime_ms": _runtime_metrics(durations),
        "dimension_coverage": {
            "registered_dimensions": len(DIMENSIONS),
            "expected_dimensions": sum(
                counts["expected_cases"] > 0 for counts in dimension_counts.values()
            ),
            "observed_dimensions": sum(
                counts["observed_cases"] > 0 for counts in dimension_counts.values()
            ),
        },
        "dimension_metrics": dimension_counts,
    }
    return {
        "schema_version": "1.0",
        "metrics": metrics,
        "cases": results,
        "failures": [result for result in results if not result["exact_match"]],
    }


def render_markdown(result: Mapping[str, Any], environment: Mapping[str, Any]) -> str:
    """Render a concise human-readable benchmark report."""

    metrics = result["metrics"]
    case_metrics = metrics["case_level"]
    block_metrics = metrics["blocking_case_level"]
    runtime = metrics["runtime_ms"]
    lines = [
        "# ego-webqa benchmark",
        "",
        f"- Generated: `{environment.get('generated_at', '')}`",
        f"- Tool: `ego-webqa {environment.get('tool_version', '')}`",
        f"- Commit: `{environment.get('git_commit', '')}`",
        f"- Suite SHA-256: `{environment.get('suite_sha256', '')}`",
        f"- Browser: `{environment.get('browser', '')}`",
        f"- Execution profile: `{environment.get('execution_profile', '')}`",
        f"- Latency role: `{environment.get('latency_role', '')}`",
        "",
        "## Result",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Cases | {metrics['total_cases']} |",
        f"| Exact matches | {metrics['exact_matches']} "
        f"({_percent(metrics['exact_match_rate'])}) |",
        f"| Case precision | {_percent(case_metrics['precision'])} |",
        f"| Case recall | {_percent(case_metrics['recall'])} |",
        f"| Case F1 | {_percent(case_metrics['f1'])} |",
        f"| Case accuracy | {_percent(case_metrics['accuracy'])} |",
        f"| Blocking false-positive rate | " f"{_percent(block_metrics['false_positive_rate'])} |",
        f"| Blocking false-negative rate | " f"{_percent(block_metrics['false_negative_rate'])} |",
        f"| Runtime P50 / P95 / max | {runtime['p50']} / {runtime['p95']} / "
        f"{runtime['max']} ms |",
        "",
        "## Dimension coverage",
        "",
        f"The suite expects {metrics['dimension_coverage']['expected_dimensions']} of "
        f"{metrics['dimension_coverage']['registered_dimensions']} registered dimensions.",
        "",
        "## Mismatches",
        "",
    ]
    failures = result.get("failures", [])
    if not failures:
        lines.append("None.")
    else:
        for failure in failures:
            details = []
            if failure["missing_issue_codes"]:
                details.append(f"missing: {', '.join(failure['missing_issue_codes'])}")
            if failure["unexpected_issue_codes"]:
                details.append(f"unexpected: {', '.join(failure['unexpected_issue_codes'])}")
            if failure["severity_mismatches"]:
                details.append(f"severity: {', '.join(failure['severity_mismatches'])}")
            if failure["error"]:
                details.append(f"runtime error: {failure['error']}")
            lines.append(f"- `{failure['id']}` — {'; '.join(details) or 'mismatch'}")
    lines.extend(
        [
            "",
            "## Scope",
            "",
            "This controlled-local benchmark covers curated synthetic fixtures and local "
            "Chromium. Serial latency is a regression baseline for that corpus only. It is "
            "not evidence of real-site coverage, public-network latency, cross-browser "
            "parity, security, business correctness, or WCAG conformance.",
            "",
        ]
    )
    return "\n".join(lines)


def _validate_viewports(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise BenchmarkConfigError("benchmark suite viewports must be a non-empty object")
    parsed: dict[str, str] = {}
    for name, viewport in value.items():
        if not isinstance(name, str) or not _CASE_ID.fullmatch(name):
            raise BenchmarkConfigError(f"invalid viewport variant name {name!r}")
        if not isinstance(viewport, str) or not re.fullmatch(r"\d+x\d+(?::[^:]+)?", viewport):
            raise BenchmarkConfigError(f"invalid viewport value for {name!r}: {viewport!r}")
        parsed[name] = viewport
    return parsed


def _variant_names(value: Any) -> tuple[str, ...]:
    names = _unique_strings(value, "variants")
    if not names:
        raise BenchmarkConfigError("variants must contain at least one viewport")
    return names


def _expected_severities(value: Any, expected: tuple[str, ...]) -> dict[str, Severity]:
    if not isinstance(value, dict):
        raise BenchmarkConfigError("expected_severities must be an object")
    result: dict[str, Severity] = {}
    for code, severity in value.items():
        if code not in expected:
            raise BenchmarkConfigError(
                f"expected_severities references undeclared expected code {code!r}"
            )
        if severity not in {"error", "warning"}:
            raise BenchmarkConfigError(f"expected severity for {code!r} must be error or warning")
        result[code] = severity
    return result


def _expected_severity(case: BenchmarkCase, code: str) -> Severity:
    override = case.expected_severities.get(code)
    if override is not None:
        return override
    return "error" if DIMENSIONS[code].default_severity == "block" else "warning"


def _unique_strings(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise BenchmarkConfigError(f"{name} must be a list of non-empty strings")
    if len(value) != len(set(value)):
        raise BenchmarkConfigError(f"{name} must not contain duplicates")
    return tuple(value)


def _required_string(item: Mapping[str, Any], key: str, owner: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BenchmarkConfigError(f"{owner} requires a non-empty {key}")
    return value.strip()


def _optional_string(item: Mapping[str, Any], key: str, default: str) -> str:
    value = item.get(key, default)
    if not isinstance(value, str):
        raise BenchmarkConfigError(f"{key} must be a string")
    return value


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _f1(tp: int, fp: int, fn: int) -> float:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0


def _runtime_metrics(values: Sequence[int]) -> dict[str, int | float]:
    if not values:
        return {"count": 0, "mean": 0, "p50": 0, "p95": 0, "max": 0}
    ordered = sorted(values)

    def percentile(fraction: float) -> int:
        index = max(0, math.ceil(len(ordered) * fraction) - 1)
        return ordered[index]

    return {
        "count": len(ordered),
        "mean": round(sum(ordered) / len(ordered), 1),
        "p50": percentile(0.50),
        "p95": percentile(0.95),
        "max": ordered[-1],
    }


def _percent(value: float) -> str:
    return f"{value * 100:.2f}%"
