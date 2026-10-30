from __future__ import annotations

import io
import json
import sys
from dataclasses import dataclass

import pytest

from ego_webqa import cli
from ego_webqa.cli import _json_text, _settings, build_parser
from ego_webqa.config import (
    HTTP_HEADERS_ENV,
    HTTP_PASSWORD_ENV,
    HTTP_USERNAME_ENV,
    Viewport,
)
from ego_webqa.doctor import DoctorCheck, DoctorReport
from ego_webqa.installer import BrowserInstallResult


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


def test_cli_quick_preset_overrides_config_matrix_and_rejects_ambiguity() -> None:
    args = build_parser().parse_args(["https://example.com", "--preset", "quick"])
    cfg = _settings(args)
    assert len(cfg.viewports) == 4
    assert {viewport.width for viewport in cfg.viewports} == {360, 390}

    conflicting = build_parser().parse_args(
        ["https://example.com", "--preset", "quick", "--viewports", "390x844:phone"]
    )
    with pytest.raises(ValueError, match="cannot be combined"):
        _settings(conflicting)


def test_cli_selects_named_bounded_flow_from_config(tmp_path) -> None:
    config_path = tmp_path / "flows.json"
    config_path.write_text(
        json.dumps(
            {
                "smoke_flows": {
                    "login": [
                        {"action": "click", "selector": "#login"},
                        {"action": "expect_visible", "selector": "#welcome"},
                    ],
                    "search": [
                        {"action": "fill", "selector": "#query", "value": "delivery"},
                        {"action": "click", "selector": "#search"},
                        {"action": "expect_visible", "selector": "#results"},
                    ],
                },
                "smoke_flow_name": "login",
            }
        ),
        encoding="utf-8",
    )
    args = build_parser().parse_args(
        [
            "https://example.com",
            "--config",
            str(config_path),
            "--smoke-flow-name",
            "search",
        ]
    )
    cfg = _settings(args)
    assert cfg.smoke_flow_name == "search"
    assert [step.action for step in cfg.active_smoke_flow] == ["fill", "click", "expect_visible"]


def test_cli_browser_engine_override() -> None:
    args = build_parser().parse_args(["https://example.com", "--browser-engine", "webkit"])
    cfg = _settings(args)
    assert cfg.browser_engine == "webkit"
    assert cfg.browser_channel == ""

    conflicting = build_parser().parse_args(
        ["https://example.com", "--browser-engine", "webkit", "--browser-channel", "msedge"]
    )
    with pytest.raises(ValueError, match="only supported with Chromium"):
        _settings(conflicting)


def test_cli_mcp_subcommand_starts_the_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_mcp_main() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("ego_webqa.mcp_server.main", fake_mcp_main)
    assert cli.main(["mcp"]) == 0
    assert called is True


def test_cli_mcp_subcommand_rejects_extra_arguments(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["mcp", "--help"]) == 2
    assert "does not accept arguments" in capsys.readouterr().err


def test_cli_doctor_json_uses_shared_diagnostic_contract(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    @dataclass(frozen=True)
    class Check:
        id: str
        status: str
        message: str
        hint: str

        def to_dict(self) -> dict[str, str]:
            return {
                "id": self.id,
                "status": self.status,
                "message": self.message,
                "hint": self.hint,
            }

    @dataclass(frozen=True)
    class Report:
        status: str
        checks: tuple[Check, ...]
        runtime: dict[str, str]

        def to_dict(self) -> dict[str, object]:
            return {
                "status": self.status,
                "runtime": self.runtime,
                "checks": [check.to_dict() for check in self.checks],
            }

    monkeypatch.setattr(
        "ego_webqa.cli.collect_doctor_report",
        lambda engine, channel: Report(
            "ok",
            (Check("python", "ok", "Python 3.12.0", ""),),
            {"browser_engine": engine, "browser_channel": channel},
        ),
    )
    assert cli.main(["doctor", "--json", "--browser-channel", "msedge"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["runtime"] == {
        "browser_engine": "chromium",
        "browser_channel": "msedge",
    }


def test_cli_doctor_failure_returns_one(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    @dataclass(frozen=True)
    class Check:
        id: str
        status: str
        message: str
        hint: str

    @dataclass(frozen=True)
    class Report:
        status: str
        checks: tuple[Check, ...]
        runtime: dict[str, str]

    monkeypatch.setattr(
        "ego_webqa.cli.collect_doctor_report",
        lambda engine, channel: Report(
            "fail",
            (Check("browser_launch", "fail", "launch failed", "install chromium"),),
            {},
        ),
    )
    assert cli.main(["doctor"]) == 1
    output = capsys.readouterr().out
    assert "FAIL browser_launch: launch failed" in output
    assert "install chromium" in output


def test_cli_install_browser_json_and_option_forwarding(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    seen: dict[str, object] = {}
    verification = DoctorReport(
        status="ok",
        checks=(DoctorCheck("browser_launch", "ok", "chromium launched successfully"),),
        runtime={"browser_engine": "chromium"},
    )

    def fake_install(engine: str, **options: object) -> BrowserInstallResult:
        seen.update({"engine": engine, **options})
        return BrowserInstallResult(
            status="ok",
            engine="chromium",
            command=(sys.executable, "-m", "playwright", "install", "--force", "chromium"),
            dry_run=False,
            returncode=0,
            verification=verification,
            detail="chromium is installed and launched successfully",
        )

    monkeypatch.setattr("ego_webqa.cli.install_browser", fake_install)

    assert (
        cli.main(
            [
                "install-browser",
                "--browser-engine",
                "chromium",
                "--with-deps",
                "--force",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert seen == {
        "engine": "chromium",
        "with_deps": True,
        "force": True,
        "dry_run": False,
        "machine_readable": True,
        "headless_only": True,
    }
    assert payload["status"] == "ok"
    assert payload["engine"] == "chromium"
    assert payload["verification"]["status"] == "ok"
    assert payload["command"][-1] == "chromium"


def test_cli_install_browser_human_dry_run_and_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "ego_webqa.cli.install_browser",
        lambda *args, **kwargs: BrowserInstallResult(
            status="planned",
            engine="chromium",
            command=(sys.executable, "-m", "playwright", "install", "chromium"),
            dry_run=True,
            returncode=None,
            verification=None,
            detail="installation and launch verification were not run",
        ),
    )
    assert cli.main(["install-browser", "--dry-run"]) == 0
    dry_run = capsys.readouterr().out
    assert "PLANNED" in dry_run
    assert "playwright install chromium" in dry_run
    assert "without --dry-run" in dry_run

    failed_checks = DoctorReport(
        status="fail",
        checks=(
            DoctorCheck(
                "browser_launch",
                "fail",
                "launch failed",
                "install Linux dependencies",
            ),
        ),
        runtime={},
    )
    monkeypatch.setattr(
        "ego_webqa.cli.install_browser",
        lambda *args, **kwargs: BrowserInstallResult(
            status="fail",
            engine="chromium",
            command=(sys.executable, "-m", "playwright", "install", "chromium"),
            dry_run=False,
            returncode=0,
            verification=failed_checks,
            detail="browser installed but verification failed: browser_launch",
        ),
    )
    assert cli.main(["install-browser"]) == 1
    failure = capsys.readouterr().out
    assert "FAIL browser_launch: launch failed" in failure
    assert "install Linux dependencies" in failure


def test_cli_setup_json_and_ready_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from ego_webqa.installer import SetupResult

    ready = DoctorReport(
        status="ok",
        checks=(DoctorCheck("browser_launch", "ok", "chromium launched successfully"),),
        runtime={"browser_runtime": "headless-shell"},
    )
    seen: dict[str, object] = {}

    def fake_setup(engine: str, **options: object) -> SetupResult:
        seen.update({"engine": engine, **options})
        return SetupResult(
            status="ok",
            engine="chromium",
            command=(sys.executable, "-m", "playwright", "install", "--only-shell", "chromium"),
            headless_only=True,
            with_deps=False,
            force=False,
            dry_run=False,
            initial_doctor=ready,
            install=None,
            detail="chromium is already installed and launched successfully",
        )

    monkeypatch.setattr("ego_webqa.cli.setup_environment", fake_setup)

    assert cli.main(["setup", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert seen == {
        "engine": "chromium",
        "with_deps": False,
        "force": False,
        "dry_run": False,
        "machine_readable": True,
        "headless_only": True,
    }
    assert payload["action"] == "setup"
    assert payload["initial_doctor"]["status"] == "ok"

    assert cli.main(["setup"]) == 0
    output = capsys.readouterr().out
    assert "Ready: ego-webqa https://your-preview.example" in output


def test_cli_setup_rejects_invalid_mode_and_reports_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def reject(*args: object, **kwargs: object) -> None:
        raise ValueError("full-browser selection applies only to Chromium")

    monkeypatch.setattr("ego_webqa.cli.setup_environment", reject)

    assert cli.main(["setup", "--browser-engine", "firefox", "--full-chromium"]) == 2
    assert "only to Chromium" in capsys.readouterr().err


def test_cli_install_browser_rejects_platform_specific_options(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def reject(*args: object, **kwargs: object) -> None:
        raise ValueError("--with-deps is supported only on Linux")

    monkeypatch.setattr("ego_webqa.cli.install_browser", reject)

    assert cli.main(["install-browser", "--with-deps"]) == 2
    assert "only on Linux" in capsys.readouterr().err


def test_cli_install_browser_full_chromium_mode_is_explicit(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    seen: dict[str, object] = {}

    def fake_install(engine: str, **options: object) -> BrowserInstallResult:
        seen.update({"engine": engine, **options})
        return BrowserInstallResult(
            status="ok",
            engine="chromium",
            command=(sys.executable, "-m", "playwright", "install", "chromium"),
            dry_run=False,
            returncode=0,
            verification=None,
            detail="chromium is installed and launched successfully",
            headless_only=False,
        )

    monkeypatch.setattr("ego_webqa.cli.install_browser", fake_install)

    assert cli.main(["install-browser", "--full-chromium"]) == 0
    assert seen["headless_only"] is False
    assert "mode: full browser" in capsys.readouterr().out


def test_cli_setup_reports_a_failed_final_verification(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from ego_webqa.installer import SetupResult

    failed = DoctorReport(
        status="fail",
        checks=(DoctorCheck("browser_launch", "fail", "launch failed", "retry setup"),),
        runtime={},
    )
    install = BrowserInstallResult(
        status="fail",
        engine="chromium",
        command=(sys.executable, "-m", "playwright", "install", "--only-shell", "chromium"),
        dry_run=False,
        returncode=0,
        verification=failed,
        detail="browser installed but verification failed: browser_launch",
    )
    monkeypatch.setattr(
        "ego_webqa.cli.setup_environment",
        lambda *args, **kwargs: SetupResult(
            status="fail",
            engine="chromium",
            command=install.command,
            headless_only=True,
            with_deps=False,
            force=False,
            dry_run=False,
            initial_doctor=failed,
            install=install,
            detail=install.detail,
        ),
    )

    assert cli.main(["setup"]) == 1
    output = capsys.readouterr().out
    assert "initial FAIL browser_launch" in output
    assert "final FAIL browser_launch" in output
    assert "retry setup" in output


def test_json_output_escapes_unsupported_stdout_encoding() -> None:
    payload = {"cta_pattern": "开始|立即"}
    portable = _json_text(payload, "cp1252")
    assert json.loads(portable) == payload
    assert "\\u5f00\\u59cb" in portable
    assert "开始" in _json_text(payload, "utf-8")


def test_console_streams_survive_a_legacy_windows_code_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    stderr = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)

    cli._configure_console_streams()
    print("browser warning: ╔══╗", file=sys.stdout)
    sys.stdout.flush()

    assert b"\\u2554" in stdout.buffer.getvalue()
    assert b"\\u2550" in stdout.buffer.getvalue()


def test_cli_main_configures_console_streams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured: list[bool] = []
    monkeypatch.setattr(cli, "_configure_console_streams", lambda: configured.append(True))

    assert cli.main(["setup", "--dry-run"]) == 0
    assert configured == [True]


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
