from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from ego_webqa import doctor


class FakeBrowser:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeBrowserType:
    def __init__(self, executable: Path | None) -> None:
        self.executable_path = str(executable or "/missing/browser")
        self.launches: list[dict[str, object]] = []
        self.browser = FakeBrowser()

    def launch(self, **options: object) -> FakeBrowser:
        self.launches.append(options)
        return self.browser


class FakePlaywright:
    def __init__(self, browser_type: FakeBrowserType) -> None:
        self.chromium = browser_type
        self.firefox = browser_type
        self.webkit = browser_type


class FakeSyncPlaywright:
    def __init__(self, browser_type: FakeBrowserType) -> None:
        self.browser_type = browser_type
        self.exited = False

    def __enter__(self) -> FakePlaywright:
        return FakePlaywright(self.browser_type)

    def __exit__(self, *_: object) -> None:
        self.exited = True


def test_doctor_reports_success_and_launches_selected_channel(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "chromium"
    executable.write_text("", encoding="utf-8")
    browser_type = FakeBrowserType(executable)
    sync = FakeSyncPlaywright(browser_type)
    monkeypatch.setattr(doctor, "_distribution_version", lambda name: f"{name}-version")
    monkeypatch.setattr(
        doctor.importlib,
        "import_module",
        lambda name: SimpleNamespace(sync_playwright=lambda: sync),
    )

    report = doctor.collect_doctor_report("chromium", "msedge")

    assert report.status == "ok"
    assert browser_type.launches == [{"headless": True, "timeout": 15_000, "channel": "msedge"}]
    assert browser_type.browser.closed is True
    assert sync.exited is True
    assert {check.id for check in report.checks} == {
        "python",
        "ego_webqa",
        "mcp",
        "playwright_package",
        "playwright_import",
        "browser_launch",
        "browser_channel",
    }
    assert report.runtime["environment"] in {"system", "isolated"}
    assert report.runtime["python_executable"]
    assert report.runtime["python_prefix"]


def test_doctor_channel_does_not_require_the_bundled_browser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser_type = FakeBrowserType(None)
    sync = FakeSyncPlaywright(browser_type)
    monkeypatch.setattr(doctor, "_distribution_version", lambda name: "1.0")
    monkeypatch.setattr(
        doctor.importlib,
        "import_module",
        lambda name: SimpleNamespace(sync_playwright=lambda: sync),
    )

    report = doctor.collect_doctor_report("chromium", "chrome")

    assert report.status == "ok"
    browser_binary = next(check for check in report.checks if check.id == "browser_channel")
    assert browser_binary.status == "ok"


def test_doctor_stops_when_playwright_package_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        doctor,
        "_distribution_version",
        lambda name: None if name == "playwright" else "2.0",
    )

    report = doctor.collect_doctor_report()

    assert report.status == "fail"
    assert report.checks[-1].id == "playwright_package"
    assert report.checks[-1].status == "fail"


def test_doctor_reports_missing_browser_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync = FakeSyncPlaywright(FakeBrowserType(None))
    monkeypatch.setattr(doctor, "_distribution_version", lambda name: "1.0")
    monkeypatch.setattr(
        doctor.importlib,
        "import_module",
        lambda name: SimpleNamespace(sync_playwright=lambda: sync),
    )

    report = doctor.collect_doctor_report()

    assert report.status == "fail"
    browser = next(check for check in report.checks if check.id == "browser_binary")
    assert browser.status == "fail"
    assert "ego-webqa install-browser --browser-engine chromium" in browser.hint
    assert report.runtime["browser_executable"].endswith("missing/browser")


def test_doctor_rejects_channel_for_non_chromium(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "firefox"
    executable.write_text("", encoding="utf-8")
    sync = FakeSyncPlaywright(FakeBrowserType(executable))
    monkeypatch.setattr(doctor, "_distribution_version", lambda name: "1.0")
    monkeypatch.setattr(
        doctor.importlib,
        "import_module",
        lambda name: SimpleNamespace(sync_playwright=lambda: sync),
    )

    report = doctor.collect_doctor_report("firefox", "msedge")

    assert report.status == "fail"
    assert report.checks[-1].id == "browser_channel"


def test_doctor_reports_playwright_import_and_launch_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(doctor, "_distribution_version", lambda name: "1.0")
    monkeypatch.setattr(
        doctor.importlib,
        "import_module",
        lambda name: (_ for _ in ()).throw(ImportError("broken import")),
    )
    missing_import = doctor.collect_doctor_report()
    assert missing_import.status == "fail"
    assert missing_import.checks[-1].id == "playwright_import"

    executable = tmp_path / "chromium"
    executable.write_text("", encoding="utf-8")

    class BrokenBrowserType(FakeBrowserType):
        def launch(self, **options: object) -> FakeBrowser:
            raise RuntimeError("no display")

    sync = FakeSyncPlaywright(BrokenBrowserType(executable))
    monkeypatch.setattr(
        doctor.importlib,
        "import_module",
        lambda name: SimpleNamespace(sync_playwright=lambda: sync),
    )
    launch_failure = doctor.collect_doctor_report()
    assert launch_failure.status == "fail"
    assert launch_failure.checks[-1].id == "browser_launch"
    assert "no display" in launch_failure.checks[-1].message
    assert "ego-webqa install-browser --browser-engine chromium" in (launch_failure.checks[-1].hint)
