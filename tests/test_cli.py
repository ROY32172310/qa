from __future__ import annotations

import json

import pytest

from ego_webqa.cli import _settings, build_parser
from ego_webqa.config import (
    HTTP_HEADERS_ENV,
    HTTP_PASSWORD_ENV,
    HTTP_USERNAME_ENV,
    Viewport,
)


@pytest.fixture(autouse=True)
def clear_auth_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (HTTP_USERNAME_ENV, HTTP_PASSWORD_ENV, HTTP_HEADERS_ENV):
        monkeypatch.delenv(name, raising=False)


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
            "--smoke-scope",
            "all",
            "--smoke-settle-ms",
            "120",
            "--smoke-require-assertion",
            "--storage-state",
            "auth.json",
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
    assert cfg.smoke_scope == "all"
    assert cfg.smoke_settle_ms == 120
    assert cfg.smoke_require_assertion is True
    assert cfg.storage_state == "auth.json"


def test_cli_live_smoke_override() -> None:
    args = build_parser().parse_args(["https://example.com", "--smoke-mode", "live"])
    assert _settings(args).smoke_mode == "live"


def test_cli_auth_environment_keeps_secrets_off_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(HTTP_USERNAME_ENV, "preview-user")
    monkeypatch.setenv(HTTP_PASSWORD_ENV, "preview-password")
    monkeypatch.setenv(
        HTTP_HEADERS_ENV,
        json.dumps({"Authorization": "Bearer secret", "X-Preview": "agent-a"}),
    )
    args = build_parser().parse_args(["https://example.com"])
    cfg = _settings(args)
    assert cfg.http_username == "preview-user"
    assert cfg.http_password == "preview-password"
    assert dict(cfg.extra_http_headers) == {
        "Authorization": "Bearer secret",
        "X-Preview": "agent-a",
    }


def test_cli_auth_environment_rejects_non_object_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(HTTP_HEADERS_ENV, "[]")
    args = build_parser().parse_args(["https://example.com"])
    with pytest.raises(ValueError, match="JSON object"):
        _settings(args)
