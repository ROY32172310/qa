"""Public API for ego-webqa."""

from __future__ import annotations

from .config import Settings, Viewport
from .engine import AuditRuntimeError, audit
from .models import AuditReport, Issue

__all__ = [
    "AuditReport",
    "AuditRuntimeError",
    "Issue",
    "Settings",
    "Viewport",
    "audit",
]

__version__ = "0.2.1"
