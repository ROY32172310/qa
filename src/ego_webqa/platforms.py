"""Small standard-library-only boundary for host platform differences."""

from __future__ import annotations

import platform
from pathlib import Path


def system_name() -> str:
    """Return the host operating-system family without leaking it into callers."""

    return platform.system()


def is_linux() -> bool:
    """Return whether Linux package-manager operations are supported."""

    return system_name() == "Linux"


def native_path(value: str) -> Path:
    """Convert a path-shaped value using the host's native path semantics."""

    return Path(value)
