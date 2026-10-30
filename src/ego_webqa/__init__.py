"""Public API for ego-webqa."""

from __future__ import annotations

from .config import (
    DimensionOverride,
    OverrideResolution,
    Settings,
    SmokeStep,
    Viewport,
    resolve_overrides,
)
from .dimensions import DIMENSIONS, Dimension, dimension_for, registry_payload
from .engine import AuditRuntimeError, audit
from .models import AuditReport, Issue

__all__ = [
    "AuditReport",
    "AuditRuntimeError",
    "DIMENSIONS",
    "Dimension",
    "DimensionOverride",
    "Issue",
    "OverrideResolution",
    "Settings",
    "SmokeStep",
    "Viewport",
    "audit",
    "dimension_for",
    "registry_payload",
    "resolve_overrides",
]

__version__ = "0.8.2"
