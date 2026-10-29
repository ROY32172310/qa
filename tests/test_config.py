from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType

import pytest

from ego_webqa.config import Settings, SmokeStep, Viewport, load_settings


def test_viewport_parse_named_and_default() -> None:
    assert Viewport.parse("390x844:mobile") == Viewport(390, 844, "mobile", mobile=True)
    assert Viewport.parse("390x844:desktop").mobile is True
    assert Viewport.parse("1280x800").name == "1280x800"
    assert Viewport.parse("390x844:mobile-enlarged@1.5~34") == Viewport(
        390,
        844,
        "mobile-enlarged",
        mobile=True,
        text_scale=1.5,
        safe_area_bottom_px=34,
    )


def test_default_viewport_matrix_is_narrow_text_scaled_and_safe_area_aware() -> None:
    viewports = Settings().viewports
    assert len(viewports) == 8
    assert {viewport.width for viewport in viewports} == {360, 390}
    assert {viewport.text_scale for viewport in viewports} == {1.0, 1.5}
    assert {viewport.safe_area_bottom_px for viewport in viewports} == {0, 34}
    assert len({viewport.name for viewport in viewports}) == 8


@pytest.mark.parametrize(
    "value",
    [
        "",
        "390",
        "a x b",
        "100x300",
        "390x844:extra:name",
        "390x844:mobile@wide",
        "390x844:mobile~safe",
        "390x844:mobile@0.5",
        "390x844:mobile@2.5",
        "390x844:mobile~101",
    ],
)
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
    with pytest.raises(ValueError, match="aspect_min_rendered_px"):
        Settings(aspect_min_rendered_px=0)
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


def test_mapping_accepts_bounded_smoke_flow_and_redacts_fill_values() -> None:
    settings = Settings.from_mapping(
        {
            "smoke_flow": [
                {"action": "fill", "selector": "#email", "value": "secret@example.com"},
                {"action": "click", "selector": "#continue"},
                {"action": "expect_visible", "selector": "#success"},
                {"action": "expect_url", "pattern": r"#complete$"},
            ]
        }
    )
    assert [step.action for step in settings.smoke_flow] == [
        "fill",
        "click",
        "expect_visible",
        "expect_url",
    ]
    payload = settings.to_dict()
    assert payload["smoke_flow"][0]["value"] == "<redacted>"
    assert "secret@example.com" not in json.dumps(payload)


@pytest.mark.parametrize(
    ("steps", "message"),
    [
        ([{"action": "click", "selector": "#next"}], "requires an expect_visible"),
        (
            [{"action": "expect_visible", "selector": "#done"}],
            "requires at least one click",
        ),
        (
            [
                {"action": "expect_visible", "selector": "#done"},
                {"action": "click", "selector": "#next"},
            ],
            "assertion after an action",
        ),
        ([{"action": "submit", "selector": "#next"}], "action must be one of"),
        ([{"action": "press", "selector": "#input"}], "press requires key"),
        ([{"action": "expect_url", "pattern": "["}], "invalid smoke_flow URL pattern"),
        (
            [
                {"action": "click", "selector": "#next"},
                {"action": "expect_visible", "selector": "#done", "value": "unexpected"},
            ],
            "value is only valid",
        ),
    ],
)
def test_smoke_flow_rejects_ambiguous_or_unbounded_steps(
    steps: list[dict[str, str]],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        Settings.from_mapping({"smoke_flow": steps})


def test_smoke_flow_is_bounded_and_mutually_exclusive_with_single_cta() -> None:
    steps = (
        SmokeStep("click", selector="#next"),
        SmokeStep("expect_visible", selector="#done"),
    )
    with pytest.raises(ValueError, match="at most 8"):
        Settings(smoke_flow=steps * 5)
    with pytest.raises(ValueError, match="cannot be combined"):
        Settings(smoke_flow=steps, smoke_selector="#next")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"action": 1}, "smoke_flow action must be a string"),
        ({"action": "click", "selector": 1}, "smoke_flow selector must be a string"),
        ({"action": "fill", "selector": "#email", "value": 1}, "smoke_flow value must be a string"),
        ({"action": "press", "selector": "#email", "key": 1}, "smoke_flow key must be a string"),
        (
            {"action": "expect_url", "pattern": 1},
            "smoke_flow pattern must be a string",
        ),
    ],
)
def test_smoke_step_rejects_non_string_fields(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        SmokeStep(**kwargs)  # type: ignore[arg-type]


def test_example_flow_config_loads() -> None:
    path = Path(__file__).resolve().parents[1] / "examples" / "webqa-flow.json"
    settings = load_settings(path)
    assert [step.action for step in settings.smoke_flow] == [
        "fill",
        "click",
        "expect_visible",
        "expect_url",
    ]


def test_authenticated_settings_are_immutable_and_redacted() -> None:
    settings = Settings(
        extra_http_headers={
            "Authorization": "Bearer top-secret",
            "X-Preview-Key": "header-secret",
        },
        storage_state="/tmp/session.json",
        http_username="preview-user",
        http_password="password-secret",
        metadata={"agent": "qa"},
    )
    assert isinstance(settings.extra_http_headers, MappingProxyType)
    assert isinstance(settings.metadata, MappingProxyType)
    payload = settings.to_dict()
    assert payload["extra_http_headers"] == {
        "Authorization": "<redacted>",
        "X-Preview-Key": "<redacted>",
    }
    assert payload["storage_state"] is True
    assert payload["http_username"] == "<redacted>"
    assert payload["http_password"] == "<redacted>"
    serialized = json.dumps(payload)
    assert "top-secret" not in serialized
    assert "header-secret" not in serialized
    assert "password-secret" not in serialized


@pytest.mark.parametrize(
    ("headers", "message"),
    [
        ({"Bad:Name": "ok"}, "invalid HTTP header name"),
        ({"": "ok"}, "invalid HTTP header name"),
        ({"X-Test": "line\r\ninjection"}, "contains a newline"),
    ],
)
def test_http_header_injection_is_rejected(
    headers: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        Settings(extra_http_headers=headers)


def test_smoke_and_auth_contract_validation() -> None:
    with pytest.raises(ValueError, match="smoke_scope"):
        Settings(smoke_scope="everywhere")
    with pytest.raises(ValueError, match="smoke_settle_ms"):
        Settings(smoke_settle_ms=-1)
    with pytest.raises(ValueError, match="smoke_require_assertion"):
        Settings(smoke_require_assertion=True)
    with pytest.raises(ValueError, match="configured together"):
        Settings(http_username="user")


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
    with pytest.raises(ValueError, match="text_scale must be a number"):
        Viewport(390, 844, text_scale="1.5")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="safe_area_bottom_px must be an integer"):
        Viewport(390, 844, safe_area_bottom_px=34.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="viewport.name must be a string"):
        Viewport(390, 844, name=1)  # type: ignore[arg-type]
