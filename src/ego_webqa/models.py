"""Stable report entities used by the CLI and API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Severity = Literal["error", "warning"]
Status = Literal["pass", "warn", "fail"]
JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Issue:
    code: str
    severity: Severity
    message: str
    viewport: str = ""
    hint: str = ""
    evidence: JsonObject = field(default_factory=dict)
    severity_source: str = "default"
    override: JsonObject = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "viewport": self.viewport,
            "message": self.message,
            "hint": self.hint,
            "evidence": dict(self.evidence),
            "severity_source": self.severity_source,
            "override": dict(self.override),
        }


@dataclass(slots=True)
class AuditReport:
    target: str
    status: Status
    issues: list[Issue]
    viewports: list[dict[str, Any]]
    smoke: dict[str, Any]
    screenshots: list[str]
    started_at: str
    duration_ms: int
    settings: dict[str, Any]
    runtime: dict[str, Any] = field(default_factory=dict)
    smoke_runs: list[dict[str, Any]] = field(default_factory=list)
    governance: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        counts = {
            "error": sum(issue.severity == "error" for issue in self.issues),
            "warning": sum(issue.severity == "warning" for issue in self.issues),
        }
        return {
            "schema_version": self.schema_version,
            "tool": "ego-webqa",
            "target": self.target,
            "status": self.status,
            "counts": counts,
            "started_at": self.started_at,
            "duration_ms": self.duration_ms,
            "issues": [issue.to_dict() for issue in self.issues],
            "viewports": self.viewports,
            "smoke": self.smoke,
            "smoke_runs": self.smoke_runs,
            "screenshots": self.screenshots,
            "settings": self.settings,
            "runtime": self.runtime,
            "governance": self.governance,
        }


def derive_status(issues: list[Issue], fail_on_warn: bool = False) -> Status:
    if any(issue.severity == "error" for issue in issues):
        return "fail"
    if issues and fail_on_warn:
        return "fail"
    return "warn" if issues else "pass"
