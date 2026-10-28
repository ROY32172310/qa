"""Standalone configuration and thresholds.

This module is the source of truth for the open-source package. It deliberately
does not import another ego package.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, get_type_hints

DEFAULT_CTA_PATTERN = (
    r"开始|立即|马上|提交|预约|预订|下单|购买|报名|领取|生成|创建|保存|发送|"
    r"查看|试试|去支付|记一笔|记账|显示|释义|认识|再来|绘制|计算|"
    r"start|get started|continue|submit|book|buy|sign up|create|save|send|view|try|checkout"
)
DEFAULT_NAV_PATTERN = (
    r"首页|返回|上一|下一|更多|登录|注册|导航|home|back|previous|next|more|login|sign in|"
    r"sign up|register|navigation|nav"
)
MOBILE_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
)
HTTP_USERNAME_ENV = "EGO_WEBQA_HTTP_USERNAME"
HTTP_PASSWORD_ENV = "EGO_WEBQA_HTTP_PASSWORD"
HTTP_HEADERS_ENV = "EGO_WEBQA_EXTRA_HTTP_HEADERS"


@dataclass(frozen=True, slots=True)
class Viewport:
    """A browser viewport used by the deterministic check matrix."""

    width: int
    height: int
    name: str = ""
    device_scale_factor: float = 1.0
    mobile: bool = False
    user_agent: str = ""

    def __post_init__(self) -> None:
        if type(self.width) is not int or type(self.height) is not int:
            raise ValueError("viewport dimensions must be integers")
        if self.width < 200 or self.height < 200:
            raise ValueError("viewport dimensions must both be at least 200")
        if type(self.device_scale_factor) not in {int, float}:
            raise ValueError("device_scale_factor must be a number")
        if self.device_scale_factor <= 0:
            raise ValueError("device_scale_factor must be positive")
        if not isinstance(self.mobile, bool):
            raise ValueError("viewport.mobile must be a boolean")
        if not isinstance(self.user_agent, str):
            raise ValueError("viewport.user_agent must be a string")
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
        width = int(match.group(1))
        mobile = width <= 600 or name.lower() in {"mobile", "phone"}
        return cls(width, int(match.group(2)), name, mobile=mobile)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "device_scale_factor": self.device_scale_factor,
            "mobile": self.mobile,
            "user_agent": self.user_agent,
        }


DEFAULT_VIEWPORTS = (
    Viewport(390, 844, "mobile", mobile=True),
    Viewport(768, 1024, "tablet"),
    Viewport(1280, 800, "desktop"),
)


@dataclass(frozen=True, slots=True)
class Settings:
    """All deterministic checks are configured here, with no hidden selectors."""

    viewports: tuple[Viewport, ...] = DEFAULT_VIEWPORTS
    profile: str = "baseline"
    timeout_ms: int = 15_000
    settle_ms: int = 350
    ready_selector: str = ""
    wait_for_network_idle: bool = False
    min_tap_target_px: float = 44.0
    hard_font_px: float = 10.0
    min_font_px: float = 12.0
    small_issue_report_min: int = 3
    overlay_ratio: float = 0.4
    overflow_tolerance_px: int = 2
    aspect_tolerance: float = 0.05
    aspect_min_rendered_px: float = 48.0
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
    smoke_success_selector: str = ""
    smoke_success_url_pattern: str = ""
    smoke_scope: str = "first"
    smoke_settle_ms: int = 800
    smoke_require_assertion: bool = False
    smoke_mode: str = "safe"
    ignore_selectors: tuple[str, ...] = ()
    ignore_console_patterns: tuple[str, ...] = ()
    ignore_request_patterns: tuple[str, ...] = ()
    extra_http_headers: Mapping[str, str] = field(default_factory=dict)
    storage_state: str = ""
    http_username: str = ""
    http_password: str = ""
    browser_channel: str = ""
    fail_on_warn: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._validate_types()
        object.__setattr__(
            self,
            "extra_http_headers",
            MappingProxyType(dict(self.extra_http_headers)),
        )
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
        if self.profile not in {"baseline", "accessibility"}:
            raise ValueError("profile must be 'baseline' or 'accessibility'")
        if not self.viewports:
            raise ValueError("at least one viewport is required")
        if len(self.viewports) > 12:
            raise ValueError("at most 12 viewports are supported")
        if self.timeout_ms < 1 or self.settle_ms < 0:
            raise ValueError("timeouts must be non-negative")
        positive = {
            "min_tap_target_px": self.min_tap_target_px,
            "hard_font_px": self.hard_font_px,
            "min_font_px": self.min_font_px,
            "aspect_min_rendered_px": self.aspect_min_rendered_px,
        }
        for name, value in positive.items():
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        non_negative = {
            "small_issue_report_min": self.small_issue_report_min,
            "overflow_tolerance_px": self.overflow_tolerance_px,
            "blank_text_chars": self.blank_text_chars,
            "blank_element_count": self.blank_element_count,
            "fcp_warn_ms": self.fcp_warn_ms,
            "transfer_warn_bytes": self.transfer_warn_bytes,
            "request_warn_count": self.request_warn_count,
        }
        for name, value in non_negative.items():
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.min_font_px < self.hard_font_px:
            raise ValueError("min_font_px must be greater than or equal to hard_font_px")
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
        if self.smoke_mode not in {"safe", "live"}:
            raise ValueError("smoke_mode must be 'safe' or 'live'")
        if self.smoke_scope not in {"first", "all"}:
            raise ValueError("smoke_scope must be 'first' or 'all'")
        if self.smoke_settle_ms < 0:
            raise ValueError("smoke_settle_ms must be non-negative")
        if self.smoke_require_assertion and not (
            self.smoke_success_selector or self.smoke_success_url_pattern
        ):
            raise ValueError(
                "smoke_require_assertion requires smoke_success_selector "
                "or smoke_success_url_pattern"
            )
        if bool(self.http_username) != bool(self.http_password):
            raise ValueError("http_username and http_password must be configured together")
        for header_name, header_value in self.extra_http_headers.items():
            if not isinstance(header_name, str) or not isinstance(header_value, str):
                raise ValueError("extra_http_headers must map strings to strings")
            if not header_name or "\r" in header_name or "\n" in header_name or ":" in header_name:
                raise ValueError(f"invalid HTTP header name: {header_name!r}")
            if "\r" in header_value or "\n" in header_value:
                raise ValueError(f"HTTP header {header_name!r} contains a newline")
        try:
            re.compile(self.cta_pattern)
            re.compile(self.nav_pattern)
            if self.smoke_success_url_pattern:
                re.compile(self.smoke_success_url_pattern)
            for pattern in self.ignore_console_patterns:
                re.compile(pattern)
            for pattern in self.ignore_request_patterns:
                re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"invalid configuration regular expression: {exc}") from exc

    def _validate_types(self) -> None:
        hints = get_type_hints(type(self))
        for name in type(self).__dataclass_fields__:
            value = getattr(self, name)
            if name == "viewports":
                if not isinstance(value, tuple) or not all(
                    isinstance(item, Viewport) for item in value
                ):
                    raise ValueError("viewports must be a tuple of Viewport values")
            elif name in {
                "ignore_console_patterns",
                "ignore_request_patterns",
                "ignore_selectors",
            }:
                if not isinstance(value, tuple) or not all(isinstance(item, str) for item in value):
                    raise ValueError(f"{name} must be a tuple of strings")
            else:
                _validate_scalar_type(name, value, hints[name])

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
            elif key in {
                "ignore_console_patterns",
                "ignore_request_patterns",
                "ignore_selectors",
            }:
                if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                    raise ValueError(f"{key} must be a list of strings")
                changes[key] = tuple(value)
            elif key == "metadata":
                if not isinstance(value, dict):
                    raise ValueError("metadata must be an object")
                changes[key] = dict(value)
            elif key == "extra_http_headers":
                if not isinstance(value, dict) or not all(
                    isinstance(name, str) and isinstance(item, str) for name, item in value.items()
                ):
                    raise ValueError("extra_http_headers must be an object of strings")
                changes[key] = dict(value)
            else:
                hints = get_type_hints(cls)
                changes[key] = _coerce_mapping_scalar(key, value, hints[key])
        return replace(current, **changes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "viewports": [viewport.to_dict() for viewport in self.viewports],
            "profile": self.profile,
            "timeout_ms": self.timeout_ms,
            "settle_ms": self.settle_ms,
            "ready_selector": self.ready_selector,
            "wait_for_network_idle": self.wait_for_network_idle,
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
            "smoke_success_selector": self.smoke_success_selector,
            "smoke_success_url_pattern": self.smoke_success_url_pattern,
            "smoke_scope": self.smoke_scope,
            "smoke_settle_ms": self.smoke_settle_ms,
            "smoke_require_assertion": self.smoke_require_assertion,
            "smoke_mode": self.smoke_mode,
            "ignore_selectors": list(self.ignore_selectors),
            "ignore_console_patterns": list(self.ignore_console_patterns),
            "ignore_request_patterns": list(self.ignore_request_patterns),
            "extra_http_headers": {name: "<redacted>" for name in sorted(self.extra_http_headers)},
            "storage_state": bool(self.storage_state),
            "http_username": "<redacted>" if self.http_username else "",
            "http_password": "<redacted>" if self.http_password else "",
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


def apply_auth_environment(settings: Settings) -> Settings:
    """Apply preview credentials from environment variables."""

    updates: dict[str, Any] = {}
    username = os.environ.get(HTTP_USERNAME_ENV)
    password = os.environ.get(HTTP_PASSWORD_ENV)
    if username is not None or password is not None:
        updates["http_username"] = username or ""
        updates["http_password"] = password or ""
    headers = os.environ.get(HTTP_HEADERS_ENV)
    if headers:
        try:
            parsed_headers = json.loads(headers)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{HTTP_HEADERS_ENV} must contain a JSON object") from exc
        if not isinstance(parsed_headers, dict):
            raise ValueError(f"{HTTP_HEADERS_ENV} must contain a JSON object")
        updates["extra_http_headers"] = parsed_headers
    return Settings.from_mapping(updates, base=settings)


def _coerce_mapping_scalar(name: str, value: Any, expected: Any) -> Any:
    if expected is bool:
        if type(value) is not bool:
            raise ValueError(f"{name} must be a boolean")
        return value
    if expected is int:
        if type(value) is not int:
            raise ValueError(f"{name} must be an integer")
        return value
    if expected is float:
        if type(value) not in {int, float}:
            raise ValueError(f"{name} must be a number")
        return float(value)
    if expected is str:
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        return value
    raise ValueError(f"{name} does not support JSON configuration")


def _validate_scalar_type(name: str, value: Any, expected: Any) -> None:
    if expected is bool:
        valid = type(value) is bool
    elif expected is int:
        valid = type(value) is int
    elif expected is float:
        valid = type(value) in {int, float}
    elif expected is str:
        valid = isinstance(value, str)
    elif expected is Mapping or getattr(expected, "__origin__", None) is Mapping:
        valid = isinstance(value, Mapping)
    else:
        valid = True
    if not valid:
        raise ValueError(f"{name} has an invalid type")
