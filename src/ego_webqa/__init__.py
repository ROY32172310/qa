"""Public API for ego-webqa."""

from __future__ import annotations

from .config import Settings, Viewport
from .dimensions import DIMENSIONS, Dimension, dimension_for, registry_payload
from .engine import AuditRuntimeError, audit
from .models import AuditReport, Issue

__all__ = [
    "AuditReport",
    "AuditRuntimeError",
    "DIMENSIONS",
    "Dimension",
    "Issue",
    "Settings",
    "Viewport",
    "audit",
    "dimension_for",
    "registry_payload",
]

__version__ = "0.2.3"
