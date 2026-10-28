from __future__ import annotations

import json
from pathlib import Path

import pytest

from ego_webqa.config import Settings, Viewport, load_settings


def test_viewport_parse_named_and_default() -> None:
    assert Viewport.parse("390x844:mobile") == Viewport(390, 844, "mobile", mobile=True)
    assert Viewport.parse("390x844:desktop").mobile is True
    assert Viewport.parse("1280x800").name == "1280x800"


@pytest.mark.parametrize("value", ["", "390", "a x b", "100x300", "390x844:extra:name"])
def test_viewport_parse_rejects_invalid(value: str) -> None:
    with pytest.raises(ValueError):
        Viewport.parse(value)


def test_load_settings_json_and_unknown_key(tmp_path: Path) -> None:
    path = tmp_path / "webqa.json"
    path.write_text(
        json.dumps({"viewports": ["390x844:phone"], "min_font_px": 13}),
        encoding="utf-8",
    )
    cfg = load_settings(path)
    assert cfg.viewports == (Viewport(390, 844, "phone", mobile=True),)
    assert cfg.min_font_px == 13

    path.write_text(json.dumps({"typo": 1}), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown config"):
        load_settings(path)


def test_invalid_threshold_is_rejected() -> None:
    with pytest.raises(ValueError, match="overlay_ratio"):
        Settings(overlay_ratio=1.2)
    with pytest.raises(ValueError, match="regular expression"):
        Settings(ignore_console_patterns=("[",))
    with pytest.raises(ValueError, match="regular expression"):
        Settings(smoke_success_url_pattern="[")
    with pytest.raises(ValueError, match="profile"):
        Settings(profile="wcag")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("timeout_ms", "15000", "timeout_ms must be an integer"),
        ("min_tap_target_px", -1, "min_tap_target_px must be positive"),
        ("transfer_warn_bytes", -10, "transfer_warn_bytes must be non-negative"),
        ("fail_on_warn", 1, "fail_on_warn must be a boolean"),
        ("smoke_mode", "unsafe", "smoke_mode must be 'safe' or 'live'"),
        ("cta_pattern", 42, "cta_pattern must be a string"),
    ],
)
def test_mapping_rejects_invalid_field_types_and_ranges(
    field: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        Settings.from_mapping({field: value})


def test_mapping_accepts_noise_patterns() -> None:
    settings = Settings.from_mapping(
        {
            "ready_selector": "#ready",
            "wait_for_network_idle": True,
            "ignore_console_patterns": ["third-party-widget"],
            "ignore_request_patterns": ["/analytics/"],
            "smoke_success_selector": "#success",
            "smoke_success_url_pattern": "/complete$",
            "profile": "accessibility",
        }
    )
    assert settings.ready_selector == "#ready"
    assert settings.wait_for_network_idle is True
    assert settings.ignore_console_patterns == ("third-party-widget",)
    assert settings.ignore_request_patterns == ("/analytics/",)
    assert settings.smoke_success_selector == "#success"
    assert settings.smoke_success_url_pattern == "/complete$"
    assert settings.profile == "accessibility"


def test_direct_settings_rejects_invalid_types() -> None:
    with pytest.raises(ValueError, match="timeout_ms has an invalid type"):
        Settings(timeout_ms="15000")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="fail_on_warn has an invalid type"):
        Settings(fail_on_warn=1)  # type: ignore[arg-type]


def test_viewport_count_is_bounded() -> None:
    portrait = Viewport(390, 844, "phone", mobile=True)
    with pytest.raises(ValueError, match="at most 12 viewports"):
        Settings(viewports=(portrait,) * 13)


def test_viewport_rejects_invalid_field_types() -> None:
    with pytest.raises(ValueError, match="dimensions must be integers"):
        Viewport("390", 844)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="device_scale_factor must be a number"):
        Viewport(390, 844, device_scale_factor="2")  # type: ignore[arg-type]
