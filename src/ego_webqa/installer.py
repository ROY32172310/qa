"""Explicit, verifiable Playwright browser installation."""

from __future__ import annotations

import platform
import subprocess
import sys
from dataclasses import dataclass
from typing import Literal, TextIO

from .doctor import DoctorReport, collect_doctor_report

BrowserEngine = Literal["chromium", "firefox", "webkit"]
InstallStatus = Literal["ok", "fail", "planned"]
BROWSER_ENGINES: tuple[BrowserEngine, ...] = ("chromium", "firefox", "webkit")


@dataclass(frozen=True, slots=True)
class BrowserInstallResult:
    """Result of an explicit browser installation attempt."""

    status: InstallStatus
    engine: BrowserEngine
    command: tuple[str, ...]
    dry_run: bool
    returncode: int | None
    verification: DoctorReport | None
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": "1.0",
            "tool": "ego-webqa",
            "action": "install-browser",
            "status": self.status,
            "engine": self.engine,
            "dry_run": self.dry_run,
            "command": list(self.command),
            "python_executable": sys.executable,
            "returncode": self.returncode,
            "detail": self.detail,
        }
        if self.verification is not None:
            payload["verification"] = self.verification.to_dict()
        return payload


def browser_install_command(
    engine: BrowserEngine = "chromium",
    *,
    with_deps: bool = False,
    force: bool = False,
) -> tuple[str, ...]:
    """Build a Playwright command for the active Python environment."""

    if engine not in BROWSER_ENGINES:
        raise ValueError(f"unsupported browser engine: {engine!r}")
    if with_deps and platform.system() != "Linux":
        raise ValueError("--with-deps is supported only on Linux")
    command = [sys.executable, "-m", "playwright", "install"]
    if with_deps:
        command.append("--with-deps")
    if force:
        command.append("--force")
    command.append(engine)
    return tuple(command)


def install_browser(
    engine: BrowserEngine = "chromium",
    *,
    with_deps: bool = False,
    force: bool = False,
    dry_run: bool = False,
    machine_readable: bool = False,
) -> BrowserInstallResult:
    """Install one browser, then verify a real headless launch.

    Browser downloads are deliberately never triggered by ``doctor`` or
    ``audit``. This explicit command owns all network and system side effects.
    """

    command = browser_install_command(engine, with_deps=with_deps, force=force)
    if dry_run:
        return BrowserInstallResult(
            status="planned",
            engine=engine,
            command=command,
            dry_run=True,
            returncode=None,
            verification=None,
            detail="installation and launch verification were not run",
        )

    installer_stdout: int | TextIO | None = sys.stderr if machine_readable else None
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdout=installer_stdout,
        )
    except OSError as exc:
        return BrowserInstallResult(
            status="fail",
            engine=engine,
            command=command,
            dry_run=False,
            returncode=None,
            verification=None,
            detail=f"could not start the Playwright installer: {exc}",
        )

    if completed.returncode != 0:
        return BrowserInstallResult(
            status="fail",
            engine=engine,
            command=command,
            dry_run=False,
            returncode=completed.returncode,
            verification=None,
            detail=f"Playwright installer exited with status {completed.returncode}",
        )

    verification = collect_doctor_report(engine)
    if verification.status == "ok":
        return BrowserInstallResult(
            status="ok",
            engine=engine,
            command=command,
            dry_run=False,
            returncode=completed.returncode,
            verification=verification,
            detail=f"{engine} is installed and launched successfully",
        )

    failed_checks = ", ".join(check.id for check in verification.checks if check.status == "fail")
    return BrowserInstallResult(
        status="fail",
        engine=engine,
        command=command,
        dry_run=False,
        returncode=completed.returncode,
        verification=verification,
        detail=f"browser installed but verification failed: {failed_checks}",
    )
