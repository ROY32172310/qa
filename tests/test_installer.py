from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

from ego_webqa import installer
from ego_webqa.doctor import DoctorCheck, DoctorReport


def _doctor_report(status: str = "ok") -> DoctorReport:
    checks = (
        DoctorCheck("playwright_package", "ok", "Playwright 1.64.1"),
        DoctorCheck("browser_launch", status, "browser launch"),
    )
    return DoctorReport(status=status, checks=checks, runtime={})  # type: ignore[arg-type]


def test_browser_install_command_uses_the_active_interpreter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(installer.platform, "system", lambda: "Linux")

    assert installer.browser_install_command("webkit", force=True) == (
        sys.executable,
        "-m",
        "playwright",
        "install",
        "--force",
        "webkit",
    )
    assert installer.browser_install_command("chromium", with_deps=True) == (
        sys.executable,
        "-m",
        "playwright",
        "install",
        "--with-deps",
        "chromium",
    )


def test_browser_install_command_rejects_invalid_engine_and_platform_deps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="unsupported browser engine"):
        installer.browser_install_command("edge")  # type: ignore[arg-type]

    monkeypatch.setattr(installer.platform, "system", lambda: "Windows")
    with pytest.raises(ValueError, match="only on Linux"):
        installer.browser_install_command("chromium", with_deps=True)


def test_install_browser_dry_run_has_no_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected(*_: object, **__: object) -> None:
        raise AssertionError("dry run must not execute")

    monkeypatch.setattr(installer.subprocess, "run", unexpected)
    monkeypatch.setattr(installer, "collect_doctor_report", unexpected)

    result = installer.install_browser(dry_run=True)

    assert result.status == "planned"
    assert result.returncode is None
    assert result.verification is None
    assert result.command[-1] == "chromium"
    assert result.to_dict()["dry_run"] is True


def test_install_browser_installs_then_verifies_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[str, ...], dict[str, Any]]] = []
    report = _doctor_report()

    def run(command: tuple[str, ...], **options: Any) -> SimpleNamespace:
        calls.append((command, options))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(installer.subprocess, "run", run)
    monkeypatch.setattr(installer, "collect_doctor_report", lambda engine: report)

    result = installer.install_browser("firefox", force=True)

    assert result.status == "ok"
    assert result.returncode == 0
    assert result.verification is report
    assert calls == [
        (
            (sys.executable, "-m", "playwright", "install", "--force", "firefox"),
            {"check": False, "stdout": None},
        )
    ]
    payload = result.to_dict()
    assert payload["action"] == "install-browser"
    assert payload["engine"] == "firefox"
    assert payload["verification"] == report.to_dict()


def test_install_browser_json_mode_keeps_installer_output_off_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout: list[object] = []

    def run(_: tuple[str, ...], **options: Any) -> SimpleNamespace:
        stdout.append(options["stdout"])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(installer.subprocess, "run", run)
    monkeypatch.setattr(installer, "collect_doctor_report", lambda _: _doctor_report())

    result = installer.install_browser(machine_readable=True)

    assert result.status == "ok"
    assert stdout == [sys.stderr]


@pytest.mark.parametrize("returncode", [1, 130])
def test_install_browser_reports_installer_failure(
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
) -> None:
    monkeypatch.setattr(
        installer.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=returncode),
    )

    result = installer.install_browser()

    assert result.status == "fail"
    assert result.returncode == returncode
    assert result.verification is None
    assert str(returncode) in result.detail


def test_install_browser_reports_process_start_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_: object, **__: object) -> None:
        raise OSError("python is unavailable")

    monkeypatch.setattr(installer.subprocess, "run", fail)

    result = installer.install_browser()

    assert result.status == "fail"
    assert result.returncode is None
    assert "python is unavailable" in result.detail


def test_install_browser_requires_a_successful_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        installer.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr(installer, "collect_doctor_report", lambda _: _doctor_report("fail"))

    result = installer.install_browser()

    assert result.status == "fail"
    assert "verification failed" in result.detail
    assert "browser_launch" in result.detail
