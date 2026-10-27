"""Standalone configuration and thresholds.

This module is the source of truth for the open-source package. It deliberately
does not import another ego package.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

DEFAULT_CTA_PATTERN = (
    r"开始|立即|马上|提交|预约|预订|下单|购买|报名|领取|生成|创建|保存|发送|"
    r"查看|试试|去支付|记一笔|记账|显示|释义|认识|再来|绘制|计算|"
    r"start|get started|continue|submit|book|buy|sign up|create|save|send|view|try|checkout"
)
DEFAULT_NAV_PATTERN = (
    r"首页|返回|上一|下一|更多|登录|注册|导航|home|back|previous|next|more|login|sign in|"
    r"sign up|register|navigation|nav"
)


@dataclass(frozen=True, slots=True)
class Viewport:
    """A browser viewport used by the deterministic check matrix."""

    width: int
    height: int
    name: str = ""
    device_scale_factor: float = 1.0

    def __post_init__(self) -> None:
        if self.width < 200 or self.height < 200:
            raise ValueError("viewport dimensions must both be at least 200")
        if self.device_scale_factor <= 0:
            raise ValueError("device_scale_factor must be positive")
        if not self.name:
            object.__setattr__(self, "name", f"{self.width}x{self.height}")

    @classmethod
    def parse(cls, value: str) -> Viewport:
        """Parse ``390x844`` or ``390x844:mobile``."""

        text = value.strip()
        name = ""
        if ":" in text:
            text, name = text.rsplit(":", 1)
        match = re.fullmatch(r"(\d+)x(\d+)", text.lower())
        if not match:
            raise ValueError(f"invalid viewport {value!r}; expected WIDTHxHEIGHT[:NAME]")
        return cls(int(match.group(1)), int(match.group(2)), name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "device_scale_factor": self.device_scale_factor,
        }


DEFAULT_VIEWPORTS = (
    Viewport(390, 844, "mobile"),
    Viewport(768, 1024, "tablet"),
    Viewport(1280, 800, "desktop"),
)


@dataclass(frozen=True, slots=True)
class Settings:
    """All deterministic checks are configured here, with no hidden selectors."""

    viewports: tuple[Viewport, ...] = DEFAULT_VIEWPORTS
    timeout_ms: int = 15_000
    settle_ms: int = 350
    min_tap_target_px: float = 44.0
    hard_font_px: float = 10.0
    min_font_px: float = 12.0
    small_issue_report_min: int = 3
    overlay_ratio: float = 0.4
    overflow_tolerance_px: int = 2
    aspect_tolerance: float = 0.05
    blank_text_chars: int = 10
    blank_element_count: int = 5
    fcp_warn_ms: float = 3_000.0
    cls_warn: float = 0.1
    cls_error: float = 0.25
    transfer_warn_bytes: int = 400_000
    transfer_error_bytes: int = 1_500_000
    request_warn_count: int = 30
    request_error_count: int = 60
    cta_pattern: str = DEFAULT_CTA_PATTERN
    nav_pattern: str = DEFAULT_NAV_PATTERN
    smoke_selector: str = ""
    ignore_selectors: tuple[str, ...] = ()
    browser_channel: str = ""
    fail_on_warn: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.viewports:
            raise ValueError("at least one viewport is required")
        if self.timeout_ms < 1 or self.settle_ms < 0:
            raise ValueError("timeouts must be non-negative")
        ratios = {
            "overlay_ratio": self.overlay_ratio,
            "aspect_tolerance": self.aspect_tolerance,
            "cls_warn": self.cls_warn,
            "cls_error": self.cls_error,
        }
        for name, value in ratios.items():
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.cls_error < self.cls_warn:
            raise ValueError("cls_error must be greater than or equal to cls_warn")
        if self.transfer_error_bytes < self.transfer_warn_bytes:
            raise ValueError("transfer_error_bytes must be >= transfer_warn_bytes")
        if self.request_error_count < self.request_warn_count:
            raise ValueError("request_error_count must be >= request_warn_count")
        try:
            re.compile(self.cta_pattern)
            re.compile(self.nav_pattern)
        except re.error as exc:
            raise ValueError(f"invalid CTA/navigation regular expression: {exc}") from exc

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any], base: Settings | None = None) -> Settings:
        """Build settings from a JSON-compatible mapping."""

        current = base or cls()
        allowed = set(cls.__dataclass_fields__)
        unknown = sorted(set(values) - allowed)
        if unknown:
            raise ValueError(f"unknown config key(s): {', '.join(unknown)}")

        changes: dict[str, Any] = {}
        for key, value in values.items():
            if key == "viewports":
                if not isinstance(value, list) or not value:
                    raise ValueError("viewports must be a non-empty list")
                changes[key] = tuple(
                    item if isinstance(item, Viewport) else Viewport.parse(str(item))
                    for item in value
                )
            elif key == "ignore_selectors":
                if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                    raise ValueError("ignore_selectors must be a list of strings")
                changes[key] = tuple(value)
            elif key == "metadata":
                if not isinstance(value, dict):
                    raise ValueError("metadata must be an object")
                changes[key] = dict(value)
            else:
                changes[key] = value
        return replace(current, **changes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "viewports": [viewport.to_dict() for viewport in self.viewports],
            "timeout_ms": self.timeout_ms,
            "settle_ms": self.settle_ms,
            "min_tap_target_px": self.min_tap_target_px,
            "hard_font_px": self.hard_font_px,
            "min_font_px": self.min_font_px,
            "small_issue_report_min": self.small_issue_report_min,
            "overlay_ratio": self.overlay_ratio,
            "overflow_tolerance_px": self.overflow_tolerance_px,
            "aspect_tolerance": self.aspect_tolerance,
            "blank_text_chars": self.blank_text_chars,
            "blank_element_count": self.blank_element_count,
            "fcp_warn_ms": self.fcp_warn_ms,
            "cls_warn": self.cls_warn,
            "cls_error": self.cls_error,
            "transfer_warn_bytes": self.transfer_warn_bytes,
            "transfer_error_bytes": self.transfer_error_bytes,
            "request_warn_count": self.request_warn_count,
            "request_error_count": self.request_error_count,
            "cta_pattern": self.cta_pattern,
            "nav_pattern": self.nav_pattern,
            "smoke_selector": self.smoke_selector,
            "ignore_selectors": list(self.ignore_selectors),
            "browser_channel": self.browser_channel,
            "fail_on_warn": self.fail_on_warn,
            "metadata": dict(self.metadata),
        }


def load_settings(path: str | Path) -> Settings:
    """Load settings from a JSON file."""

    raw = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON config {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("config root must be a JSON object")
    return Settings.from_mapping(data)
