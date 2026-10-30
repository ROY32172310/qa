"""Installation and browser readiness diagnostics."""

from __future__ import annotations

import importlib
import importlib.metadata
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from . import __version__

CheckStatus = Literal["ok", "fail"]


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    id: str
    status: CheckStatus
    message: str
    hint: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "status": self.status,
            "message": self.message,
            "hint": self.hint,
        }


@dataclass(frozen=True, slots=True)
class DoctorReport:
    status: CheckStatus
    checks: tuple[DoctorCheck, ...]
    runtime: dict[str, str]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "tool": "ego-webqa",
            "status": self.status,
            "runtime": dict(self.runtime),
            "checks": [check.to_dict() for check in self.checks],
        }


def _distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _required_check(check_id: str, message: str, hint: str = "") -> DoctorCheck:
    return DoctorCheck(check_id, "ok", message, hint)


def _failed_check(check_id: str, message: str, hint: str = "") -> DoctorCheck:
    return DoctorCheck(check_id, "fail", message, hint)


def collect_doctor_report(
    browser_engine: str = "chromium",
    browser_channel: str = "",
) -> DoctorReport:
    """Check the local Python, MCP, and Playwright browser installation."""

    checks: list[DoctorCheck] = []
    browser_executable = ""

    # The package cannot import on a Python older than its declared minimum.
    checks.append(_required_check("python", f"Python {platform.python_version()}"))

    checks.append(_required_check("ego_webqa", f"ego-webqa {__version__}"))

    mcp_version = _distribution_version("mcp")
    if mcp_version:
        checks.append(_required_check("mcp", f"MCP SDK {mcp_version}"))
    else:
        checks.append(
            _failed_check(
                "mcp",
                "MCP SDK is not installed",
                'Run: python -m pip install "ego-webqa".',
            )
        )

    playwright_version = _distribution_version("playwright")
    if not playwright_version:
        checks.append(
            _failed_check(
                "playwright_package",
                "Playwright package is not installed",
                "Reinstall ego-webqa in this Python environment, then retry.",
            )
        )
        return _report(
            checks,
            browser_engine,
            browser_channel,
            playwright_version or "",
            browser_executable,
        )

    checks.append(_required_check("playwright_package", f"Playwright {playwright_version}"))

    try:
        sync_api = importlib.import_module("playwright.sync_api")
        sync_playwright = sync_api.sync_playwright
    except (ImportError, AttributeError) as exc:
        checks.append(
            _failed_check(
                "playwright_import",
                f"Playwright import failed: {exc}",
                "Reinstall ego-webqa in this Python environment, then retry.",
            )
        )
        return _report(
            checks,
            browser_engine,
            browser_channel,
            playwright_version,
            browser_executable,
        )

    checks.append(_required_check("playwright_import", "Playwright import"))

    try:
        with sync_playwright() as playwright:
            browser_type = getattr(playwright, browser_engine)
            label = browser_engine
            launch_options: dict[str, object] = {
                "headless": True,
                "timeout": 15_000,
            }
            if browser_channel:
                if browser_engine != "chromium":
                    checks.append(
                        _failed_check(
                            "browser_channel",
                            f"{browser_engine} does not support browser channels",
                            "Use chromium with --browser-channel or remove the channel.",
                        )
                    )
                    return _report(
                        checks,
                        browser_engine,
                        browser_channel,
                        playwright_version,
                        browser_executable,
                    )
                launch_options["channel"] = browser_channel
                label = browser_channel
            else:
                executable = Path(str(browser_type.executable_path))
                browser_executable = str(executable)
                if not executable.is_file():
                    checks.append(
                        _failed_check(
                            "browser_binary",
                            f"{browser_engine} browser binary is missing at {executable}",
                            (
                                "Run: ego-webqa install-browser "
                                f"--browser-engine {browser_engine}"
                            ),
                        )
                    )
                    return _report(
                        checks,
                        browser_engine,
                        browser_channel,
                        playwright_version,
                        browser_executable,
                    )
                checks.append(
                    _required_check(
                        "browser_binary",
                        f"{browser_engine} executable found at {executable}",
                    )
                )
            browser = browser_type.launch(**launch_options)
            browser.close()
            checks.append(_required_check("browser_launch", f"{label} launched successfully"))
            if browser_channel:
                checks.append(
                    _required_check(
                        "browser_channel",
                        f"{browser_channel} system channel launched successfully",
                    )
                )
    except Exception as exc:  # Playwright raises several platform-specific exception types.
        hint = (
            f"Install {browser_channel}, or run: ego-webqa install-browser "
            f"--browser-engine {browser_engine}"
            if browser_channel
            else (
                "Run: ego-webqa install-browser "
                f"--browser-engine {browser_engine}; on Linux use "
                "ego-webqa install-browser --with-deps if system libraries are missing"
            )
        )
        checks.append(
            _failed_check(
                "browser_launch",
                f"{browser_engine} launch failed: {exc}",
                hint,
            )
        )

    return _report(
        checks,
        browser_engine,
        browser_channel,
        playwright_version,
        browser_executable,
    )


def _report(
    checks: list[DoctorCheck],
    browser_engine: str,
    browser_channel: str,
    playwright_version: str,
    browser_executable: str,
) -> DoctorReport:
    status: CheckStatus = "fail" if any(check.status == "fail" for check in checks) else "ok"
    return DoctorReport(
        status=status,
        checks=tuple(checks),
        runtime={
            "platform": platform.platform(),
            "python": platform.python_version(),
            "python_executable": sys.executable,
            "python_prefix": sys.prefix,
            "environment": "isolated" if sys.prefix != sys.base_prefix else "system",
            "playwright": playwright_version,
            "browser_engine": browser_engine,
            "browser_channel": browser_channel,
            "browser_executable": browser_executable,
        },
    )
