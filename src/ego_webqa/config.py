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
from datetime import date, datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, get_type_hints

from .dimensions import dimension_for

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
SMOKE_STEP_ACTIONS = frozenset({"click", "fill", "press", "expect_visible", "expect_url"})
BROWSER_ENGINES = frozenset({"chromium", "firefox", "webkit"})
OVERRIDE_SEVERITIES = frozenset({"block", "warn"})
OVERRIDABLE_PARAMETER_FIELDS = MappingProxyType(
    {
        "overflow_tolerance_px": "overflow_tolerance_px",
        "blank_text_chars": "blank_text_chars",
        "blank_element_count": "blank_element_count",
        "hard_font_px": "hard_font_px",
        "min_font_px": "min_font_px",
        "small_issue_report_min": "small_issue_report_min",
        "min_tap_target_px": "min_tap_target_px",
        "overlay_ratio": "overlay_ratio",
        "aspect_tolerance": "aspect_tolerance",
        "aspect_min_rendered_px": "aspect_min_rendered_px",
        "fcp_warn_ms": "fcp_warn_ms",
        "cls_warn": "cls_warn",
        "cls_error": "cls_error",
        "transfer_warn_bytes": "transfer_warn_bytes",
        "transfer_error_bytes": "transfer_error_bytes",
        "request_warn_count": "request_warn_count",
        "request_error_count": "request_error_count",
    }
)
OVERRIDABLE_PARAMETER_TYPES = MappingProxyType(
    {
        "overflow_tolerance_px": int,
        "blank_text_chars": int,
        "blank_element_count": int,
        "hard_font_px": float,
        "min_font_px": float,
        "small_issue_report_min": int,
        "min_tap_target_px": float,
        "overlay_ratio": float,
        "aspect_tolerance": float,
        "aspect_min_rendered_px": float,
        "fcp_warn_ms": float,
        "cls_warn": float,
        "cls_error": float,
        "transfer_warn_bytes": int,
        "transfer_error_bytes": int,
        "request_warn_count": int,
        "request_error_count": int,
    }
)
OVERRIDE_SEVERITY_TO_ISSUE = MappingProxyType({"block": "error", "warn": "warning"})


@dataclass(frozen=True, slots=True)
class DimensionOverride:
    """One governed, expiring adjustment to a registered dimension."""

    dimension_id: str
    reason: str
    owner: str
    expires: str
    severity: str = ""
    parameters: Mapping[str, int | float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("dimension_id", "reason", "owner", "expires", "severity"):
            if not isinstance(getattr(self, name), str):
                raise ValueError(f"override {name} must be a string")
        dimension_id = self.dimension_id.strip()
        reason = self.reason.strip()
        owner = self.owner.strip()
        expires = self.expires.strip()
        severity = self.severity.strip()
        if not reason:
            raise ValueError("override reason is required")
        if not owner:
            raise ValueError("override owner is required")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", expires):
            raise ValueError("override expires must use YYYY-MM-DD")
        try:
            date.fromisoformat(expires)
        except ValueError as exc:
            raise ValueError(f"override expires is not a valid date: {expires}") from exc
        if severity and severity not in OVERRIDE_SEVERITIES:
            raise ValueError("override severity must be 'block' or 'warn'")
        dimension = dimension_for(dimension_id)
        if not isinstance(self.parameters, Mapping):
            raise ValueError("override parameters must be an object")
        parameters: dict[str, int | float] = {}
        for name, value in self.parameters.items():
            if not isinstance(name, str):
                raise ValueError("override parameter names must be strings")
            if name not in dimension.parameters:
                raise ValueError(
                    f"override parameter {name!r} is not exposed by dimension {dimension_id}"
                )
            expected = OVERRIDABLE_PARAMETER_TYPES.get(name)
            if expected is None or name not in OVERRIDABLE_PARAMETER_FIELDS:
                raise ValueError(f"override parameter {name!r} is not safely overridable")
            if expected is int:
                if type(value) is not int:
                    raise ValueError(f"override parameter {name} must be an integer")
                parameters[name] = value
            elif type(value) not in {int, float}:
                raise ValueError(f"override parameter {name} must be a number")
            else:
                parameters[name] = float(value)
        object.__setattr__(self, "dimension_id", dimension_id)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "owner", owner)
        object.__setattr__(self, "expires", expires)
        object.__setattr__(self, "severity", severity)
        object.__setattr__(self, "parameters", MappingProxyType(parameters))

    @property
    def expires_date(self) -> date:
        return date.fromisoformat(self.expires)

    @property
    def effective_severity(self) -> str:
        return self.severity or dimension_for(self.dimension_id).default_severity

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> DimensionOverride:
        if not isinstance(value, Mapping):
            raise ValueError("overrides entries must be objects")
        allowed = {"dimension_id", "reason", "owner", "expires", "severity", "parameters"}
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(f"unknown override key(s): {', '.join(unknown)}")
        return cls(
            dimension_id=value.get("dimension_id", ""),
            reason=value.get("reason", ""),
            owner=value.get("owner", ""),
            expires=value.get("expires", ""),
            severity=value.get("severity", ""),
            parameters=value.get("parameters", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension_id": self.dimension_id,
            "reason": self.reason,
            "owner": self.owner,
            "expires": self.expires,
            "severity": self.severity,
            "parameters": dict(self.parameters),
        }


@dataclass(frozen=True, slots=True)
class OverrideResolution:
    """Effective settings plus visible active and expired override audit data."""

    settings: Settings
    as_of: date
    active: tuple[DimensionOverride, ...]
    expired: tuple[DimensionOverride, ...]
    effective_parameters: Mapping[str, int | float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of.isoformat(),
            "active_overrides": [
                _override_audit_dict(override, status="active") for override in self.active
            ],
            "expired_overrides": [
                _override_audit_dict(override, status="expired") for override in self.expired
            ],
            "effective_parameters": dict(self.effective_parameters),
        }


@dataclass(frozen=True, slots=True)
class Viewport:
    """One concrete browser variant in the deterministic check matrix."""

    width: int
    height: int
    name: str = ""
    device_scale_factor: float = 1.0
    mobile: bool = False
    user_agent: str = ""
    text_scale: float = 1.0
    safe_area_bottom_px: int = 0

    def __post_init__(self) -> None:
        if type(self.width) is not int or type(self.height) is not int:
            raise ValueError("viewport dimensions must be integers")
        if self.width < 200 or self.height < 200:
            raise ValueError("viewport dimensions must both be at least 200")
        if type(self.device_scale_factor) not in {int, float}:
            raise ValueError("device_scale_factor must be a number")
        if self.device_scale_factor <= 0:
            raise ValueError("device_scale_factor must be positive")
        if type(self.text_scale) not in {int, float}:
            raise ValueError("text_scale must be a number")
        if not 1.0 <= self.text_scale <= 2.0:
            raise ValueError("text_scale must be between 1.0 and 2.0")
        if type(self.safe_area_bottom_px) is not int:
            raise ValueError("safe_area_bottom_px must be an integer")
        if not 0 <= self.safe_area_bottom_px <= 100:
            raise ValueError("safe_area_bottom_px must be between 0 and 100")
        if not isinstance(self.mobile, bool):
            raise ValueError("viewport.mobile must be a boolean")
        if not isinstance(self.name, str):
            raise ValueError("viewport.name must be a string")
        if not isinstance(self.user_agent, str):
            raise ValueError("viewport.user_agent must be a string")
        if not self.name:
            suffix = ""
            if self.text_scale != 1.0 or self.safe_area_bottom_px:
                suffix = f"-{round(self.text_scale * 100):g}-safe{self.safe_area_bottom_px}"
            object.__setattr__(self, "name", f"{self.width}x{self.height}{suffix}")

    @classmethod
    def parse(cls, value: str) -> Viewport:
        """Parse ``390x844[:NAME][@TEXT_SCALE][~SAFE_BOTTOM_PX]``."""

        text = value.strip()
        text_scale = 1.0
        safe_area_bottom_px = 0
        if "~" in text:
            text, raw_safe_area = text.rsplit("~", 1)
            if not re.fullmatch(r"\d+", raw_safe_area):
                raise ValueError(f"invalid safe-area value in viewport {value!r}")
            safe_area_bottom_px = int(raw_safe_area)
        if "@" in text:
            text, raw_text_scale = text.rsplit("@", 1)
            try:
                text_scale = float(raw_text_scale)
            except ValueError as exc:
                raise ValueError(f"invalid text-scale value in viewport {value!r}") from exc
        name = ""
        if ":" in text:
            text, name = text.rsplit(":", 1)
        match = re.fullmatch(r"(\d+)x(\d+)", text.lower())
        if not match:
            raise ValueError(
                f"invalid viewport {value!r}; "
                "expected WIDTHxHEIGHT[:NAME][@TEXT_SCALE][~SAFE_BOTTOM_PX]"
            )
        width = int(match.group(1))
        mobile = width <= 600 or name.lower() in {"mobile", "phone"}
        return cls(
            width,
            int(match.group(2)),
            name,
            mobile=mobile,
            text_scale=text_scale,
            safe_area_bottom_px=safe_area_bottom_px,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "device_scale_factor": self.device_scale_factor,
            "mobile": self.mobile,
            "user_agent": self.user_agent,
            "text_scale": self.text_scale,
            "safe_area_bottom_px": self.safe_area_bottom_px,
        }


@dataclass(frozen=True, slots=True)
class SmokeStep:
    """One bounded action or assertion in an optional delivery smoke flow."""

    action: str
    selector: str = ""
    value: str = ""
    key: str = ""
    pattern: str = ""

    def __post_init__(self) -> None:
        for field_name in ("action", "selector", "value", "key", "pattern"):
            if not isinstance(getattr(self, field_name), str):
                raise ValueError(f"smoke_flow {field_name} must be a string")
        if self.action not in SMOKE_STEP_ACTIONS:
            choices = ", ".join(sorted(SMOKE_STEP_ACTIONS))
            raise ValueError(f"smoke_flow action must be one of: {choices}")
        if self.action == "expect_url":
            if not self.pattern:
                raise ValueError("smoke_flow expect_url requires pattern")
            try:
                re.compile(self.pattern)
            except re.error as exc:
                raise ValueError(f"invalid smoke_flow URL pattern: {exc}") from exc
        elif not self.selector:
            raise ValueError(f"smoke_flow {self.action} requires selector")
        if self.action == "press" and not self.key:
            raise ValueError("smoke_flow press requires key")
        if self.action != "fill" and self.value:
            raise ValueError("smoke_flow value is only valid for fill")
        if self.action != "press" and self.key:
            raise ValueError("smoke_flow key is only valid for press")
        if self.action != "expect_url" and self.pattern:
            raise ValueError("smoke_flow pattern is only valid for expect_url")
        for field_name, field_value in (
            ("selector", self.selector),
            ("value", self.value),
            ("key", self.key),
            ("pattern", self.pattern),
        ):
            if len(field_value) > 1_000:
                raise ValueError(f"smoke_flow {field_name} is too long")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> SmokeStep:
        if not isinstance(value, Mapping):
            raise ValueError("smoke_flow steps must be objects")
        allowed = {"action", "selector", "value", "key", "pattern"}
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(f"unknown smoke_flow step key(s): {', '.join(unknown)}")
        for key in allowed:
            if key in value and not isinstance(value[key], str):
                raise ValueError(f"smoke_flow {key} must be a string")
        return cls(
            action=value.get("action", ""),
            selector=value.get("selector", ""),
            value=value.get("value", ""),
            key=value.get("key", ""),
            pattern=value.get("pattern", ""),
        )

    def to_dict(self) -> dict[str, str]:
        payload = {"action": self.action}
        for key in ("selector", "value", "key", "pattern"):
            value = getattr(self, key)
            if value:
                payload[key] = "<redacted>" if key == "value" and self.action == "fill" else value
        return payload


DEFAULT_VIEWPORTS = tuple(
    Viewport(
        width,
        height,
        f"mobile-{width}-{round(text_scale * 100)}-safe{safe_area_bottom_px}",
        mobile=True,
        text_scale=text_scale,
        safe_area_bottom_px=safe_area_bottom_px,
    )
    for width, height in ((360, 800), (390, 844))
    for text_scale in (1.0, 1.5)
    for safe_area_bottom_px in (0, 34)
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
    smoke_flow: tuple[SmokeStep, ...] = ()
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
    browser_engine: str = "chromium"
    overrides: tuple[DimensionOverride, ...] = ()

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
        if self.browser_engine not in BROWSER_ENGINES:
            choices = ", ".join(sorted(BROWSER_ENGINES))
            raise ValueError(f"browser_engine must be one of: {choices}")
        if self.browser_channel and self.browser_engine != "chromium":
            raise ValueError("browser_channel is only supported with Chromium")
        override_ids = [override.dimension_id for override in self.overrides]
        if len(override_ids) != len(set(override_ids)):
            raise ValueError("overrides may declare each dimension at most once")
        if self.smoke_settle_ms < 0:
            raise ValueError("smoke_settle_ms must be non-negative")
        if self.smoke_require_assertion and not (
            self.smoke_success_selector or self.smoke_success_url_pattern or self.smoke_flow
        ):
            raise ValueError(
                "smoke_require_assertion requires smoke_success_selector "
                "or smoke_success_url_pattern, or smoke_flow"
            )
        if len(self.smoke_flow) > 8:
            raise ValueError("smoke_flow supports at most 8 steps")
        if self.smoke_flow:
            if self.smoke_selector or self.smoke_success_selector or self.smoke_success_url_pattern:
                raise ValueError(
                    "smoke_flow cannot be combined with smoke_selector or "
                    "single-step success assertions"
                )
            action_actions = {"click", "fill", "press"}
            assertion_actions = {"expect_visible", "expect_url"}
            first_action = next(
                (
                    index
                    for index, step in enumerate(self.smoke_flow)
                    if step.action in action_actions
                ),
                None,
            )
            if first_action is None:
                raise ValueError("smoke_flow requires at least one click, fill, or press action")
            if not any(
                step.action in assertion_actions for step in self.smoke_flow[first_action + 1 :]
            ):
                raise ValueError(
                    "smoke_flow requires an expect_visible or expect_url assertion after an action"
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
                "smoke_flow",
                "ignore_console_patterns",
                "ignore_request_patterns",
                "ignore_selectors",
                "overrides",
            }:
                if name == "smoke_flow":
                    if not isinstance(value, tuple) or not all(
                        isinstance(item, SmokeStep) for item in value
                    ):
                        raise ValueError("smoke_flow must be a tuple of SmokeStep values")
                elif name == "overrides":
                    if not isinstance(value, tuple) or not all(
                        isinstance(item, DimensionOverride) for item in value
                    ):
                        raise ValueError("overrides must be a tuple of DimensionOverride values")
                elif not isinstance(value, tuple) or not all(
                    isinstance(item, str) for item in value
                ):
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
            elif key == "smoke_flow":
                if not isinstance(value, list):
                    raise ValueError("smoke_flow must be a list")
                changes[key] = tuple(SmokeStep.from_mapping(item) for item in value)
            elif key == "overrides":
                if not isinstance(value, list):
                    raise ValueError("overrides must be a list")
                changes[key] = tuple(DimensionOverride.from_mapping(item) for item in value)
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
            "smoke_flow": [step.to_dict() for step in self.smoke_flow],
            "ignore_selectors": list(self.ignore_selectors),
            "ignore_console_patterns": list(self.ignore_console_patterns),
            "ignore_request_patterns": list(self.ignore_request_patterns),
            "extra_http_headers": {name: "<redacted>" for name in sorted(self.extra_http_headers)},
            "storage_state": bool(self.storage_state),
            "http_username": "<redacted>" if self.http_username else "",
            "http_password": "<redacted>" if self.http_password else "",
            "browser_engine": self.browser_engine,
            "browser_channel": self.browser_channel,
            "fail_on_warn": self.fail_on_warn,
            "metadata": dict(self.metadata),
            "overrides": [override.to_dict() for override in self.overrides],
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


def resolve_overrides(
    settings: Settings,
    *,
    as_of: date | None = None,
) -> OverrideResolution:
    """Resolve active overrides into effective settings and audit data."""

    if as_of is None:
        as_of = datetime.now(timezone.utc).date()
    if type(as_of) is not date:
        raise ValueError("override as_of must be a date")

    active: list[DimensionOverride] = []
    expired: list[DimensionOverride] = []
    effective: dict[str, int | float] = {}
    owners: dict[str, tuple[int | float, str]] = {}
    for override in settings.overrides:
        if as_of > override.expires_date:
            expired.append(override)
            continue
        active.append(override)
        for parameter, value in override.parameters.items():
            field_name = OVERRIDABLE_PARAMETER_FIELDS[parameter]
            previous = owners.get(field_name)
            if previous is not None and previous[0] != value:
                raise ValueError(
                    f"conflicting overrides for {field_name}: "
                    f"{previous[1]} uses {previous[0]!r}, "
                    f"{override.dimension_id} uses {value!r}"
                )
            owners[field_name] = (value, override.dimension_id)
            effective[field_name] = value

    effective_settings = Settings.from_mapping(effective, base=settings) if effective else settings
    return OverrideResolution(
        settings=effective_settings,
        as_of=as_of,
        active=tuple(active),
        expired=tuple(expired),
        effective_parameters=MappingProxyType(effective),
    )


def _override_audit_dict(override: DimensionOverride, *, status: str) -> dict[str, Any]:
    dimension = dimension_for(override.dimension_id)
    return {
        **override.to_dict(),
        "status": status,
        "default_severity": dimension.default_severity,
        "effective_severity": override.effective_severity,
    }


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
