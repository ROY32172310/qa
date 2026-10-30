from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from types import MappingProxyType

import pytest

from ego_webqa.config import (
    BROWSER_ENGINES,
    VIEWPORT_PRESETS,
    DimensionOverride,
    Settings,
    SmokeStep,
    Viewport,
    load_settings,
    resolve_overrides,
    resolve_viewport_preset,
)


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


def test_quick_viewport_preset_is_closed_and_pairwise_balanced() -> None:
    quick = resolve_viewport_preset("quick")
    assert quick == VIEWPORT_PRESETS["quick"]
    assert len(quick) == 4
    assert len({viewport.width for viewport in quick}) == 2
    assert len({viewport.text_scale for viewport in quick}) == 2
    assert len({viewport.safe_area_bottom_px for viewport in quick}) == 2
    for width in {viewport.width for viewport in quick}:
        width_variants = [viewport for viewport in quick if viewport.width == width]
        assert {viewport.text_scale for viewport in width_variants} == {1.0, 1.5}
        assert {viewport.safe_area_bottom_px for viewport in width_variants} == {0, 34}
    assert Settings.from_mapping({"viewport_preset": "quick"}).viewports == quick
    assert Settings.from_mapping({"viewport_preset": "full"}).viewports == Settings().viewports

    with pytest.raises(ValueError, match="viewport_preset must be one of"):
        Settings.from_mapping({"viewport_preset": "tiny"})
    with pytest.raises(ValueError, match="cannot be combined"):
        Settings.from_mapping(
            {
                "viewport_preset": "quick",
                "viewports": ["390x844:phone"],
            }
        )


def test_browser_engine_defaults_to_chromium_and_accepts_preview_engines() -> None:
    assert Settings().browser_engine == "chromium"
    for engine in BROWSER_ENGINES:
        assert Settings(browser_engine=engine).to_dict()["browser_engine"] == engine
    with pytest.raises(ValueError, match="browser_engine"):
        Settings(browser_engine="safari")
    with pytest.raises(ValueError, match="only supported with Chromium"):
        Settings(browser_engine="webkit", browser_channel="msedge")


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
    with pytest.raises(ValueError, match="text_clip_tolerance_px"):
        Settings(text_clip_tolerance_px=-0.1)
    with pytest.raises(ValueError, match="regular expression"):
        Settings(ignore_console_patterns=("[",))
    with pytest.raises(ValueError, match="regular expression"):
        Settings(smoke_success_url_pattern="[")
    with pytest.raises(ValueError, match="profile"):
        Settings(profile="wcag")


@pytest.mark.parametrize(
    "field,value",
    [
        (field, value)
        for field in (
            "min_tap_target_px",
            "hard_font_px",
            "min_font_px",
            "overlay_ratio",
            "text_clip_tolerance_px",
            "aspect_tolerance",
            "aspect_min_rendered_px",
            "fcp_warn_ms",
            "cls_warn",
            "cls_error",
        )
        for value in (math.nan, math.inf, -math.inf)
    ],
)
def test_non_finite_float_settings_are_rejected(field: str, value: float) -> None:
    with pytest.raises(ValueError, match=rf"{field} must be finite"):
        Settings.from_mapping({field: value})


def test_json_config_with_non_finite_number_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "webqa.json"
    path.write_text('{"fcp_warn_ms": NaN}', encoding="utf-8")

    with pytest.raises(ValueError, match="fcp_warn_ms must be finite"):
        load_settings(path)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_viewport_scale_is_rejected(value: float) -> None:
    with pytest.raises(ValueError, match="device_scale_factor must be finite"):
        Viewport(390, 844, device_scale_factor=value)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_override_parameter_is_rejected(value: float) -> None:
    with pytest.raises(ValueError, match="min_font_px must be finite"):
        DimensionOverride(
            "tiny_fonts",
            "test",
            "qa",
            "2999-12-31",
            parameters={"min_font_px": value},
        )


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
            "text_clip_tolerance_px": 2.5,
        }
    )
    assert settings.ready_selector == "#ready"
    assert settings.wait_for_network_idle is True
    assert settings.ignore_console_patterns == ("third-party-widget",)
    assert settings.ignore_request_patterns == ("/analytics/",)
    assert settings.smoke_success_selector == "#success"
    assert settings.smoke_success_url_pattern == "/complete$"
    assert settings.profile == "accessibility"
    assert settings.text_clip_tolerance_px == 2.5


def test_mapping_accepts_bounded_smoke_flow_and_redacts_fill_values() -> None:
    settings = Settings.from_mapping(
        {
            "smoke_flow": [
                {"action": "fill", "selector": "#email", "value": "secret@example.com"},
                {"action": "click", "selector": "#continue"},
                {"action": "expect_visible", "selector": "#success"},
                {"action": "expect_url", "pattern": r"#complete$"},
                {"action": "expect_text", "selector": "#success", "pattern": "Preview"},
            ]
        }
    )
    assert [step.action for step in settings.smoke_flow] == [
        "fill",
        "click",
        "expect_visible",
        "expect_url",
        "expect_text",
    ]
    payload = settings.to_dict()
    assert payload["smoke_flow"][0]["value"] == "<redacted>"
    assert "secret@example.com" not in json.dumps(payload)


def test_named_bounded_flows_select_one_flow_and_keep_all_definitions_closed() -> None:
    settings = Settings.from_mapping(
        {
            "smoke_flows": {
                "login": [
                    {"action": "fill", "selector": "#email", "value": "qa@example.com"},
                    {"action": "click", "selector": "#continue"},
                    {"action": "expect_visible", "selector": "#welcome"},
                ],
                "checkout.v2": [
                    {"action": "click", "selector": "#buy"},
                    {"action": "expect_text", "selector": "#status", "pattern": "^paid$"},
                ],
            },
            "smoke_flow_name": "checkout.v2",
        }
    )

    assert list(settings.smoke_flows) == ["login", "checkout.v2"]
    assert [step.action for step in settings.active_smoke_flow] == ["click", "expect_text"]
    payload = settings.to_dict()
    assert payload["smoke_flow_name"] == "checkout.v2"
    assert payload["smoke_flow"][0]["selector"] == "#buy"
    assert "smoke_flows" not in payload


@pytest.mark.parametrize(
    ("values", "message"),
    [
        (
            {
                "smoke_flows": {
                    "login": [
                        {"action": "click", "selector": "#continue"},
                        {"action": "expect_visible", "selector": "#welcome"},
                    ]
                }
            },
            "smoke_flow_name is required",
        ),
        (
            {
                "smoke_flows": {
                    "login": [
                        {"action": "click", "selector": "#continue"},
                        {"action": "expect_visible", "selector": "#welcome"},
                    ]
                },
                "smoke_flow_name": "checkout",
            },
            "unknown smoke_flow_name",
        ),
        ({"smoke_flow_name": "login"}, "requires smoke_flows"),
        (
            {
                "smoke_flow": [
                    {"action": "click", "selector": "#continue"},
                    {"action": "expect_visible", "selector": "#welcome"},
                ],
                "smoke_flows": {
                    "login": [
                        {"action": "click", "selector": "#continue"},
                        {"action": "expect_visible", "selector": "#welcome"},
                    ]
                },
                "smoke_flow_name": "login",
            },
            "cannot be combined",
        ),
        (
            {
                "smoke_flows": {
                    "private flow": [
                        {"action": "click", "selector": "#continue"},
                        {"action": "expect_visible", "selector": "#welcome"},
                    ]
                },
                "smoke_flow_name": "private flow",
            },
            "names must match",
        ),
        (
            {
                "smoke_flows": {
                    "login": [
                        {"action": "click", "selector": "#continue"},
                        {"action": "expect_visible", "selector": "#welcome"},
                    ],
                    "broken": [{"action": "click", "selector": "#continue"}],
                },
                "smoke_flow_name": "login",
            },
            "requires an expect_visible",
        ),
    ],
)
def test_named_bounded_flows_reject_ambiguous_or_invalid_definitions(
    values: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        Settings.from_mapping(values)


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
            [{"action": "expect_text", "selector": "#status"}],
            "expect_text requires pattern",
        ),
        (
            [{"action": "expect_text", "pattern": "ready"}],
            "expect_text requires selector",
        ),
        (
            [{"action": "expect_text", "selector": "#status", "pattern": "["}],
            "invalid smoke_flow text pattern",
        ),
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


def test_example_named_flow_config_loads() -> None:
    path = Path(__file__).resolve().parents[1] / "examples" / "webqa-named-flows.json"
    settings = load_settings(path)
    assert len(settings.viewports) == 4
    assert set(settings.smoke_flows) == {"continue", "email"}
    assert settings.smoke_flow_name == "continue"
    assert [step.action for step in settings.active_smoke_flow] == ["click", "expect_visible"]


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


def test_governed_override_parses_and_resolves_effective_values() -> None:
    settings = Settings.from_mapping(
        {
            "overrides": [
                {
                    "dimension_id": "tiny_fonts",
                    "reason": "Typography migration tracked in DS-142",
                    "owner": "design-system",
                    "expires": "2026-11-30",
                    "severity": "block",
                    "parameters": {"min_font_px": 13},
                }
            ]
        }
    )

    assert settings.overrides == (
        DimensionOverride(
            "tiny_fonts",
            "Typography migration tracked in DS-142",
            "design-system",
            "2026-11-30",
            "block",
            {"min_font_px": 13},
        ),
    )
    resolved = resolve_overrides(settings, as_of=date(2026, 11, 30))
    assert resolved.settings.min_font_px == 13
    assert resolved.expired == ()
    assert resolved.to_dict()["active_overrides"][0]["effective_severity"] == "block"


def test_expired_override_visible_and_falls_back_to_defaults() -> None:
    settings = Settings.from_mapping(
        {
            "overrides": [
                {
                    "dimension_id": "tiny_fonts",
                    "reason": "Temporary migration exception",
                    "owner": "design-system",
                    "expires": "2026-11-30",
                    "severity": "block",
                    "parameters": {"min_font_px": 15},
                }
            ]
        }
    )

    resolved = resolve_overrides(settings, as_of=date(2026, 12, 1))
    assert resolved.settings.min_font_px == 12
    assert resolved.active == ()
    assert len(resolved.expired) == 1
    assert resolved.to_dict()["expired_overrides"][0]["status"] == "expired"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            [
                {
                    "dimension_id": "not_registered",
                    "reason": "test",
                    "owner": "qa",
                    "expires": "2026-11-30",
                }
            ],
            "unregistered",
        ),
        (
            [{"dimension_id": "tiny_fonts", "owner": "qa", "expires": "2026-11-30"}],
            "reason is required",
        ),
        (
            [{"dimension_id": "tiny_fonts", "reason": "test", "expires": "2026-11-30"}],
            "owner is required",
        ),
        (
            [{"dimension_id": "tiny_fonts", "reason": "test", "owner": "qa"}],
            "expires must use",
        ),
        (
            [
                {
                    "dimension_id": "tiny_fonts",
                    "reason": "test",
                    "owner": "qa",
                    "expires": "2026-02-30",
                }
            ],
            "not a valid date",
        ),
        (
            [
                {
                    "dimension_id": "tiny_fonts",
                    "reason": "test",
                    "owner": "qa",
                    "expires": "2026-11-30",
                    "parameters": {"not_a_parameter": 1},
                }
            ],
            "not exposed",
        ),
        (
            [
                {
                    "dimension_id": "network_idle_timeout",
                    "reason": "test",
                    "owner": "qa",
                    "expires": "2026-11-30",
                    "parameters": {"timeout_ms": 1_000},
                }
            ],
            "not safely overridable",
        ),
        (
            [
                {
                    "dimension_id": "tiny_fonts",
                    "reason": "test",
                    "owner": "qa",
                    "expires": "2026-11-30",
                    "severity": "info",
                }
            ],
            "severity must be",
        ),
        (
            [
                {
                    "dimension_id": "tiny_fonts",
                    "reason": "test",
                    "owner": "qa",
                    "expires": "2026-11-30",
                    "unexpected": True,
                }
            ],
            "unknown override key",
        ),
        (
            [
                {
                    "dimension_id": "tiny_fonts",
                    "reason": "test",
                    "owner": "qa",
                    "expires": "2026-11-30",
                    "parameters": {"min_font_px": "13"},
                }
            ],
            "must be a number",
        ),
        (
            [
                {
                    "dimension_id": "tiny_fonts",
                    "reason": "test",
                    "owner": "qa",
                    "expires": "2026-11-30",
                    "parameters": {"small_issue_report_min": 2.5},
                }
            ],
            "must be an integer",
        ),
    ],
)
def test_override_rejects_unregistered_or_incomplete_governance(
    overrides: list[dict[str, object]],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        Settings.from_mapping({"overrides": overrides})


def test_override_rejects_duplicate_dimensions_and_conflicting_shared_thresholds() -> None:
    base = {
        "reason": "temporary exception",
        "owner": "qa",
        "expires": "2026-11-30",
    }
    with pytest.raises(ValueError, match="at most once"):
        Settings.from_mapping(
            {
                "overrides": [
                    {"dimension_id": "tiny_fonts", **base},
                    {"dimension_id": "tiny_fonts", **base},
                ]
            }
        )

    settings = Settings.from_mapping(
        {
            "overrides": [
                {
                    "dimension_id": "tiny_fonts",
                    **base,
                    "parameters": {"small_issue_report_min": 2},
                },
                {
                    "dimension_id": "small_tap_targets",
                    **base,
                    "parameters": {"small_issue_report_min": 4},
                },
            ]
        }
    )
    with pytest.raises(ValueError, match="conflicting overrides"):
        resolve_overrides(settings, as_of=date(2026, 11, 1))


def test_shared_threshold_accepts_the_same_governed_value() -> None:
    base = {
        "reason": "Consistent review cadence",
        "owner": "qa",
        "expires": "2999-12-31",
        "parameters": {"small_issue_report_min": 2},
    }
    settings = Settings.from_mapping(
        {
            "overrides": [
                {"dimension_id": "tiny_fonts", **base},
                {"dimension_id": "small_tap_targets", **base},
            ]
        }
    )

    resolved = resolve_overrides(settings, as_of=date(2026, 11, 1))

    assert resolved.settings.small_issue_report_min == 2
    assert len(resolved.active) == 2


def test_clipped_text_tolerance_is_governed() -> None:
    settings = Settings.from_mapping(
        {
            "overrides": [
                {
                    "dimension_id": "clipped_text",
                    "reason": "Account for font metric rounding",
                    "owner": "design-system",
                    "expires": "2999-12-31",
                    "parameters": {"text_clip_tolerance_px": 2.5},
                }
            ]
        }
    )

    resolved = resolve_overrides(settings, as_of=date(2026, 11, 1))

    assert resolved.settings.text_clip_tolerance_px == 2.5


def test_governed_example_config_loads() -> None:
    path = Path(__file__).resolve().parents[1] / "examples" / "webqa-governed.json"
    settings = load_settings(path)
    assert settings.overrides[0].owner == "design-system"
    assert settings.overrides[0].parameters["min_font_px"] == 13


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
