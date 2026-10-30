"""Explicit, verifiable Playwright browser installation."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from typing import Literal, TextIO

from .doctor import DoctorReport, collect_doctor_report
from .platforms import is_linux

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
    headless_only: bool = True

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": "1.0",
            "tool": "ego-webqa",
            "action": "install-browser",
            "status": self.status,
            "engine": self.engine,
            "dry_run": self.dry_run,
            "headless_only": self.headless_only,
            "command": list(self.command),
            "python_executable": sys.executable,
            "returncode": self.returncode,
            "detail": self.detail,
        }
        if self.verification is not None:
            payload["verification"] = self.verification.to_dict()
        return payload


@dataclass(frozen=True, slots=True)
class SetupResult:
    """Result of the explicit one-command installation and verification path."""

    status: InstallStatus
    engine: BrowserEngine
    command: tuple[str, ...]
    headless_only: bool
    with_deps: bool
    force: bool
    dry_run: bool
    initial_doctor: DoctorReport | None
    install: BrowserInstallResult | None
    detail: str

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": "1.0",
            "tool": "ego-webqa",
            "action": "setup",
            "status": self.status,
            "engine": self.engine,
            "headless_only": self.headless_only,
            "with_deps": self.with_deps,
            "force": self.force,
            "dry_run": self.dry_run,
            "command": list(self.command),
            "python_executable": sys.executable,
            "detail": self.detail,
        }
        if self.initial_doctor is not None:
            payload["initial_doctor"] = self.initial_doctor.to_dict()
        if self.install is not None:
            payload["install"] = self.install.to_dict()
        return payload


def browser_install_command(
    engine: BrowserEngine = "chromium",
    *,
    with_deps: bool = False,
    force: bool = False,
    headless_only: bool = True,
) -> tuple[str, ...]:
    """Build a Playwright command for the active Python environment."""

    if engine not in BROWSER_ENGINES:
        raise ValueError(f"unsupported browser engine: {engine!r}")
    if not headless_only and engine != "chromium":
        raise ValueError("full-browser selection applies only to Chromium")
    if with_deps and not is_linux():
        raise ValueError("--with-deps is supported only on Linux")
    command = [sys.executable, "-m", "playwright", "install"]
    if with_deps:
        command.append("--with-deps")
    if engine == "chromium" and headless_only:
        command.append("--only-shell")
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
    headless_only: bool = True,
) -> BrowserInstallResult:
    """Install one browser, then verify a real headless launch.

    Browser downloads are deliberately never triggered by ``doctor`` or
    ``audit``. This explicit command owns all network and system side effects.
    """

    effective_headless_only = engine == "chromium" and headless_only
    command = browser_install_command(
        engine,
        with_deps=with_deps,
        force=force,
        headless_only=headless_only,
    )
    if dry_run:
        return BrowserInstallResult(
            status="planned",
            engine=engine,
            command=command,
            dry_run=True,
            returncode=None,
            verification=None,
            detail="installation and launch verification were not run",
            headless_only=effective_headless_only,
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
            headless_only=effective_headless_only,
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
            headless_only=effective_headless_only,
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
            headless_only=effective_headless_only,
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
        headless_only=effective_headless_only,
    )


def setup_environment(
    engine: BrowserEngine = "chromium",
    *,
    with_deps: bool = False,
    force: bool = False,
    dry_run: bool = False,
    machine_readable: bool = False,
    headless_only: bool = True,
) -> SetupResult:
    """Check readiness, install one browser only when needed, then verify it."""

    effective_headless_only = engine == "chromium" and headless_only
    command = browser_install_command(
        engine,
        with_deps=with_deps,
        force=force,
        headless_only=headless_only,
    )
    if dry_run:
        return SetupResult(
            status="planned",
            engine=engine,
            command=command,
            headless_only=effective_headless_only,
            with_deps=with_deps,
            force=force,
            dry_run=True,
            initial_doctor=None,
            install=None,
            detail="readiness check, installation, and launch verification were not run",
        )

    initial = collect_doctor_report(engine)
    if initial.status == "ok" and not force:
        return SetupResult(
            status="ok",
            engine=engine,
            command=command,
            headless_only=effective_headless_only,
            with_deps=with_deps,
            force=force,
            dry_run=False,
            initial_doctor=initial,
            install=None,
            detail=f"{engine} is already installed and launched successfully",
        )

    if not force and not any(
        check.id == "browser_launch" and check.status == "fail" for check in initial.checks
    ):
        return SetupResult(
            status="fail",
            engine=engine,
            command=command,
            headless_only=effective_headless_only,
            with_deps=with_deps,
            force=force,
            dry_run=False,
            initial_doctor=initial,
            install=None,
            detail="the current installation problem cannot be repaired by installing a browser",
        )

    installed = install_browser(
        engine,
        with_deps=with_deps,
        force=force,
        machine_readable=machine_readable,
        headless_only=headless_only,
    )
    return SetupResult(
        status=installed.status,
        engine=engine,
        command=command,
        headless_only=effective_headless_only,
        with_deps=with_deps,
        force=force,
        dry_run=False,
        initial_doctor=initial,
        install=installed,
        detail=installed.detail,
    )
