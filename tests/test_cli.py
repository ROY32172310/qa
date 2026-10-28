from __future__ import annotations

from ego_webqa.cli import _settings, build_parser
from ego_webqa.config import Viewport


def test_cli_viewport_and_selector_overrides() -> None:
    args = build_parser().parse_args(
        [
            "https://example.com",
            "--viewports",
            "390x844:phone,1280x800",
            "--ignore-selector",
            ".chat",
            "--ignore-console-pattern",
            "third-party",
            "--ignore-request-pattern",
            "/analytics/",
            "--ready-selector",
            "#ready",
            "--wait-for-network-idle",
            "--smoke-success-selector",
            "#success",
            "--smoke-success-url-pattern",
            "/complete$",
            "--profile",
            "accessibility",
        ]
    )
    cfg = _settings(args)
    assert cfg.viewports == (
        Viewport(390, 844, "phone", mobile=True),
        Viewport(1280, 800),
    )
    assert cfg.ignore_selectors == (".chat",)
    assert cfg.ignore_console_patterns == ("third-party",)
    assert cfg.ignore_request_patterns == ("/analytics/",)
    assert cfg.ready_selector == "#ready"
    assert cfg.wait_for_network_idle is True
    assert cfg.smoke_success_selector == "#success"
    assert cfg.smoke_success_url_pattern == "/complete$"
    assert cfg.profile == "accessibility"
    assert cfg.smoke_mode == "safe"


def test_cli_live_smoke_override() -> None:
    args = build_parser().parse_args(["https://example.com", "--smoke-mode", "live"])
    assert _settings(args).smoke_mode == "live"
