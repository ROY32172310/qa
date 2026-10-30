"""Packaged JSON Schema contracts for stable integration payloads."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

SCHEMA_NAMES = (
    "report",
    "agent-summary",
    "dimensions",
    "feedback-bundle",
    "delta",
    "doctor",
    "browser-install",
    "setup",
)


def load_schema(name: str) -> dict[str, Any]:
    """Load one packaged schema by its stable public name."""

    if name not in SCHEMA_NAMES:
        choices = ", ".join(SCHEMA_NAMES)
        raise ValueError(f"unknown schema {name!r}; expected one of: {choices}")
    resource = files("ego_webqa").joinpath("schemas").joinpath(f"{name}.schema.json")
    payload = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"packaged schema {name!r} must be a JSON object")
    return payload
