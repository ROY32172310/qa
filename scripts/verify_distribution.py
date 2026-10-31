#!/usr/bin/env python3
"""Verify public release and discovery-channel distribution state."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parent.parent
PYPI_PACKAGE = "ego-webqa"
MCP_SERVER_NAME = "io.github.ROY32172310/qa"
GITHUB_REPOSITORY = "ROY32172310/qa"
PYPI_LATEST_GRACE = timedelta(minutes=30)
GLAMA_PROFILE = "https://glama.ai/mcp/servers/ROY32172310/qa"
GLAMA_BADGE = f"{GLAMA_PROFILE}/badge"
TENSORBLOCK_PROFILE = "https://www.tensorblock.co/mcp/servers/github-roy32172310-qa-73ad3a11"
TENSORBLOCK_BADGE = (
    "https://mcp-index.tensorblock.co/v1/servers/" "github-roy32172310-qa-73ad3a11/badge.svg"
)

CheckStatus = Literal["pass", "warn", "fail"]
ReportStatus = Literal["pass", "warn", "fail"]


class DistributionError(RuntimeError):
    """A distribution request or payload could not be verified."""


@dataclass(frozen=True)
class HttpResponse:
    """The subset of an HTTP response needed by this verifier."""

    status: int
    content_type: str
    body: bytes
    url: str


class Fetcher:
    """Callable HTTP boundary that tests can replace without network access."""

    def __call__(self, url: str) -> HttpResponse:
        raise NotImplementedError


@dataclass(frozen=True)
class CheckResult:
    """One external distribution check."""

    system: str
    required: bool
    status: CheckStatus
    url: str
    detail: str
    http_status: int | None = None
    content_type: str | None = None
    observed_version: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "system": self.system,
            "required": self.required,
            "status": self.status,
            "url": self.url,
            "http_status": self.http_status,
            "content_type": self.content_type,
            "observed_version": self.observed_version,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class VerificationReport:
    """Stable evidence for one distribution verification run."""

    expected_version: str
    checked_at: str
    require_directories: bool
    checks: tuple[CheckResult, ...]

    @property
    def status(self) -> ReportStatus:
        if any(check.status == "fail" for check in self.checks):
            return "fail"
        if any(check.status == "warn" for check in self.checks):
            return "warn"
        return "pass"

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "tool": "ego-webqa-distribution-verifier",
            "expected_version": self.expected_version,
            "checked_at": self.checked_at,
            "require_directories": self.require_directories,
            "status": self.status,
            "summary": {
                "passed": sum(check.status == "pass" for check in self.checks),
                "warnings": sum(check.status == "warn" for check in self.checks),
                "failed": sum(check.status == "fail" for check in self.checks),
            },
            "checks": [check.as_dict() for check in self.checks],
        }


def _project_version() -> str:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version = "([^"]+)"$', pyproject)
    if match is None:
        raise DistributionError("pyproject.toml does not declare a project version")
    return match.group(1)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_default_fetcher(github_token: str | None = None) -> Fetcher:
    """Create the standard-library HTTP fetcher used by the CLI."""

    class DefaultFetcher(Fetcher):
        def __call__(self, url: str) -> HttpResponse:
            headers = {
                "Accept": "application/json,text/html,image/*;q=0.8,*/*;q=0.5",
                "User-Agent": "ego-webqa-distribution-verifier/1.0",
            }
            if github_token and url.startswith("https://api.github.com/"):
                headers["Authorization"] = f"Bearer {github_token}"
            request = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    return HttpResponse(
                        status=response.status,
                        content_type=response.headers.get("content-type", ""),
                        body=response.read(),
                        url=response.geturl(),
                    )
            except urllib.error.HTTPError as exc:
                return HttpResponse(
                    status=exc.code,
                    content_type=exc.headers.get("content-type", ""),
                    body=exc.read(),
                    url=exc.geturl(),
                )
            except OSError as exc:
                raise DistributionError(f"request failed for {url}: {exc}") from exc

    return DefaultFetcher()


def _request(fetcher: Fetcher, url: str) -> HttpResponse:
    try:
        return fetcher(url)
    except DistributionError:
        raise
    except OSError as exc:
        raise DistributionError(f"request failed for {url}: {exc}") from exc


def _json_object(response: HttpResponse, label: str) -> dict[str, Any]:
    if not 200 <= response.status < 300:
        raise DistributionError(f"{label} returned HTTP {response.status}")
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DistributionError(f"{label} returned malformed JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise DistributionError(f"{label} must return a JSON object")
    return payload


def _failure(
    *,
    system: str,
    required: bool,
    url: str,
    detail: str,
    response: HttpResponse | None = None,
    observed_version: str | None = None,
) -> CheckResult:
    return CheckResult(
        system=system,
        required=required,
        status="fail" if required else "warn",
        url=url,
        detail=detail,
        http_status=response.status if response is not None else None,
        content_type=response.content_type if response is not None else None,
        observed_version=observed_version,
    )


def _passing(
    *,
    system: str,
    required: bool,
    url: str,
    detail: str,
    response: HttpResponse | None = None,
    observed_version: str | None = None,
) -> CheckResult:
    return CheckResult(
        system=system,
        required=required,
        status="pass",
        url=url,
        detail=detail,
        http_status=response.status if response is not None else None,
        content_type=response.content_type if response is not None else None,
        observed_version=observed_version,
    )


def _warning(
    *,
    system: str,
    required: bool,
    url: str,
    detail: str,
    response: HttpResponse | None = None,
    observed_version: str | None = None,
) -> CheckResult:
    return CheckResult(
        system=system,
        required=required,
        status="warn",
        url=url,
        detail=detail,
        http_status=response.status if response is not None else None,
        content_type=response.content_type if response is not None else None,
        observed_version=observed_version,
    )


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _release_age_minutes(files: object, checked_at: str) -> float | None:
    if not isinstance(files, list):
        return None
    upload_times = [
        uploaded
        for item in files
        if isinstance(item, dict)
        and (uploaded := _parse_timestamp(item.get("upload_time_iso_8601"))) is not None
    ]
    checked = _parse_timestamp(checked_at)
    if not upload_times or checked is None:
        return None
    return max(0.0, (checked - min(upload_times)).total_seconds() / 60)


def _check_pypi(fetcher: Fetcher, expected_version: str, checked_at: str) -> CheckResult:
    version_url = f"https://pypi.org/pypi/{PYPI_PACKAGE}/{expected_version}/json"
    try:
        response = _request(fetcher, version_url)
        payload = _json_object(response, "PyPI version metadata")
    except DistributionError as exc:
        return _failure(system="pypi", required=True, url=version_url, detail=str(exc))

    info = payload.get("info")
    version = info.get("version") if isinstance(info, dict) else None
    if not isinstance(version, str):
        return _failure(
            system="pypi",
            required=True,
            url=version_url,
            detail="PyPI metadata does not declare info.version",
            response=response,
        )
    if version != expected_version:
        return _failure(
            system="pypi",
            required=True,
            url=version_url,
            detail=f"PyPI version endpoint returned {version}; expected {expected_version}",
            response=response,
            observed_version=version,
        )

    files = payload.get("urls")
    filenames = (
        {
            item.get("filename")
            for item in files
            if isinstance(item, dict) and isinstance(item.get("filename"), str)
        }
        if isinstance(files, list)
        else set()
    )
    wheel = any(
        isinstance(name, str)
        and name.startswith(f"ego_webqa-{expected_version}-")
        and name.endswith(".whl")
        for name in filenames
    )
    sdist = any(
        isinstance(name, str)
        and name.startswith(f"ego_webqa-{expected_version}")
        and name.endswith(".tar.gz")
        for name in filenames
    )
    if not wheel or not sdist:
        missing = ", ".join(
            label for label, present in (("wheel", wheel), ("sdist", sdist)) if not present
        )
        return _failure(
            system="pypi",
            required=True,
            url=version_url,
            detail=f"PyPI {expected_version} is missing required artifacts: {missing}",
            response=response,
            observed_version=version,
        )

    latest_url = f"https://pypi.org/pypi/{PYPI_PACKAGE}/json"
    try:
        latest_response = _request(fetcher, latest_url)
        latest_payload = _json_object(latest_response, "PyPI latest metadata")
    except DistributionError as exc:
        return _failure(system="pypi", required=True, url=latest_url, detail=str(exc))
    latest_info = latest_payload.get("info")
    latest_version = latest_info.get("version") if isinstance(latest_info, dict) else None
    if not isinstance(latest_version, str):
        return _failure(
            system="pypi",
            required=True,
            url=latest_url,
            detail="PyPI latest metadata does not declare info.version",
            response=latest_response,
        )
    if latest_version != expected_version:
        age_minutes = _release_age_minutes(files, checked_at)
        if age_minutes is not None and age_minutes < PYPI_LATEST_GRACE.total_seconds() / 60:
            return _warning(
                system="pypi",
                required=True,
                url=latest_url,
                detail=(
                    f"PyPI latest still reports {latest_version}; {expected_version} was "
                    f"uploaded {age_minutes:.1f} minutes ago, within the 30-minute cache grace"
                ),
                response=latest_response,
                observed_version=latest_version,
            )
        return _failure(
            system="pypi",
            required=True,
            url=latest_url,
            detail=f"PyPI latest is {latest_version}; expected {expected_version}",
            response=latest_response,
            observed_version=latest_version,
        )
    return _passing(
        system="pypi",
        required=True,
        url=latest_url,
        detail=f"PyPI latest is {expected_version} with wheel and sdist",
        response=latest_response,
        observed_version=latest_version,
    )


def _check_mcp_registry(fetcher: Fetcher, expected_version: str) -> CheckResult:
    url = (
        "https://registry.modelcontextprotocol.io/v0.1/servers" "?search=io.github.ROY32172310%2Fqa"
    )
    try:
        response = _request(fetcher, url)
        payload = _json_object(response, "Official MCP Registry")
    except DistributionError as exc:
        return _failure(system="official-mcp-registry", required=True, url=url, detail=str(exc))

    entries = payload.get("servers")
    versions: list[str] = []
    if isinstance(entries, list):
        for entry in entries:
            server = entry.get("server") if isinstance(entry, dict) else None
            if not isinstance(server, dict) or server.get("name") != MCP_SERVER_NAME:
                continue
            version = server.get("version")
            if isinstance(version, str):
                versions.append(version)
    if expected_version not in versions:
        observed = ", ".join(sorted(versions)) or "none"
        return _failure(
            system="official-mcp-registry",
            required=True,
            url=url,
            detail=(
                f"Official MCP Registry does not contain {MCP_SERVER_NAME}@"
                f"{expected_version}; observed: {observed}"
            ),
            response=response,
        )
    return _passing(
        system="official-mcp-registry",
        required=True,
        url=url,
        detail=f"Official MCP Registry contains {MCP_SERVER_NAME}@{expected_version}",
        response=response,
        observed_version=expected_version,
    )


def _check_github_release(fetcher: Fetcher, expected_version: str) -> CheckResult:
    tag = f"v{expected_version}"
    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/tags/{tag}"
    try:
        response = _request(fetcher, url)
        payload = _json_object(response, "GitHub Release")
    except DistributionError as exc:
        return _failure(system="github-release", required=True, url=url, detail=str(exc))

    if payload.get("tag_name") != tag:
        return _failure(
            system="github-release",
            required=True,
            url=url,
            detail=f"GitHub Release tag does not match {tag}",
            response=response,
        )
    if payload.get("draft") is not False or payload.get("prerelease") is not False:
        return _failure(
            system="github-release",
            required=True,
            url=url,
            detail="GitHub Release must be published and non-prerelease",
            response=response,
        )

    assets = payload.get("assets")
    names = (
        {
            item.get("name")
            for item in assets
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        if isinstance(assets, list)
        else set()
    )
    wheel = any(
        isinstance(name, str)
        and name.startswith(f"ego_webqa-{expected_version}-")
        and name.endswith(".whl")
        for name in names
    )
    sdist = any(
        isinstance(name, str)
        and name.startswith(f"ego_webqa-{expected_version}")
        and name.endswith(".tar.gz")
        for name in names
    )
    agensi = "web-delivery-qa-gate.zip" in names
    if not all((wheel, sdist, agensi)):
        missing = ", ".join(
            label
            for label, present in (
                ("wheel", wheel),
                ("sdist", sdist),
                ("Agensi ZIP", agensi),
            )
            if not present
        )
        return _failure(
            system="github-release",
            required=True,
            url=url,
            detail=f"GitHub Release {tag} is missing required assets: {missing}",
            response=response,
        )
    return _passing(
        system="github-release",
        required=True,
        url=url,
        detail=f"GitHub Release {tag} contains wheel, sdist, and Agensi ZIP",
        response=response,
    )


def _contains_version(response: HttpResponse, expected_version: str) -> bool:
    text = response.body.decode("utf-8", errors="replace")
    return re.search(rf"(?<![\d.]){re.escape(expected_version)}(?![\d.])", text) is not None


def _check_glama_profile(
    fetcher: Fetcher,
    expected_version: str,
    *,
    required: bool,
) -> CheckResult:
    try:
        response = _request(fetcher, GLAMA_PROFILE)
    except DistributionError as exc:
        return _failure(
            system="glama-profile",
            required=required,
            url=GLAMA_PROFILE,
            detail=str(exc),
        )
    if not 200 <= response.status < 300:
        return _failure(
            system="glama-profile",
            required=required,
            url=GLAMA_PROFILE,
            detail=f"Glama profile returned HTTP {response.status}",
            response=response,
        )
    if not _contains_version(response, expected_version):
        return _failure(
            system="glama-profile",
            required=required,
            url=GLAMA_PROFILE,
            detail=(
                f"Glama profile is reachable but does not show {expected_version}; "
                "allow directory synchronization lag"
            ),
            response=response,
        )
    return _passing(
        system="glama-profile",
        required=required,
        url=GLAMA_PROFILE,
        detail=f"Glama profile shows {expected_version}",
        response=response,
        observed_version=expected_version,
    )


def _check_image(
    fetcher: Fetcher,
    *,
    system: str,
    url: str,
    required: bool,
) -> CheckResult:
    try:
        response = _request(fetcher, url)
    except DistributionError as exc:
        return _failure(system=system, required=required, url=url, detail=str(exc))
    content_type = response.content_type.split(";", 1)[0].strip().lower()
    if not 200 <= response.status < 300:
        return _failure(
            system=system,
            required=required,
            url=url,
            detail=f"{system} returned HTTP {response.status}",
            response=response,
        )
    if not content_type.startswith("image/"):
        return _failure(
            system=system,
            required=required,
            url=url,
            detail=f"{system} returned non-image content-type {content_type or 'missing'}",
            response=response,
        )
    return _passing(
        system=system,
        required=required,
        url=url,
        detail=f"{system} is reachable as {content_type}",
        response=response,
    )


def _check_reachable(
    fetcher: Fetcher,
    *,
    system: str,
    url: str,
    required: bool,
) -> CheckResult:
    try:
        response = _request(fetcher, url)
    except DistributionError as exc:
        return _failure(system=system, required=required, url=url, detail=str(exc))
    if not 200 <= response.status < 300:
        return _failure(
            system=system,
            required=required,
            url=url,
            detail=f"{system} returned HTTP {response.status}",
            response=response,
        )
    return _passing(
        system=system,
        required=required,
        url=url,
        detail=f"{system} is reachable; its public page does not expose a stable version API",
        response=response,
    )


def verify_distribution(
    fetcher: Fetcher,
    *,
    expected_version: str,
    require_directories: bool = False,
    checked_at: str | None = None,
) -> VerificationReport:
    """Run all public distribution checks without mutating external state."""

    checked_at_value = checked_at or _utc_now()
    checks = (
        _check_pypi(fetcher, expected_version, checked_at_value),
        _check_mcp_registry(fetcher, expected_version),
        _check_github_release(fetcher, expected_version),
        _check_glama_profile(
            fetcher,
            expected_version,
            required=require_directories,
        ),
        _check_image(
            fetcher,
            system="glama-badge",
            url=GLAMA_BADGE,
            required=require_directories,
        ),
        _check_reachable(
            fetcher,
            system="tensorblock-profile",
            url=TENSORBLOCK_PROFILE,
            required=require_directories,
        ),
        _check_image(
            fetcher,
            system="tensorblock-badge",
            url=TENSORBLOCK_BADGE,
            required=require_directories,
        ),
    )
    return VerificationReport(
        expected_version=expected_version,
        checked_at=checked_at_value,
        require_directories=require_directories,
        checks=checks,
    )


def render_json(report: VerificationReport) -> str:
    """Render stable, human-reviewable distribution evidence."""

    return json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n"


def render_markdown(report: VerificationReport) -> str:
    """Render a concise evidence summary for CI and release review."""

    lines = [
        "# ego-webqa distribution verification",
        "",
        f"- Expected version: `{report.expected_version}`",
        f"- Checked at: `{report.checked_at}`",
        f"- Status: **{report.status}**",
        f"- Directory checks required: `{str(report.require_directories).lower()}`",
        "",
        "| Check | Required | Status | Observed | Detail |",
        "|---|---:|---|---|---|",
    ]
    for check in report.checks:
        detail = check.detail.replace("|", "\\|").replace("\n", " ")
        observed = check.observed_version or "n/a"
        required = "yes" if check.required else "no"
        lines.append(
            f"| `{check.system}` | {required} | {check.status} | " f"`{observed}` | {detail} |"
        )
    lines.extend(
        [
            "",
            "Directory checks are observational unless `--require-directories` is set. "
            "Reachability and version synchronization do not prove adoption or "
            "product-market fit.",
            "",
        ]
    )
    return "\n".join(lines)


def write_evidence(report: VerificationReport, output_dir: Path) -> None:
    """Write JSON and Markdown evidence to deterministic filenames."""

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "distribution.json").write_text(render_json(report), encoding="utf-8")
    (output_dir / "summary.md").write_text(render_markdown(report), encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--online",
        action="store_true",
        help="confirm that public network endpoints should be queried",
    )
    parser.add_argument(
        "--version",
        default=None,
        help="expected release version (defaults to pyproject.toml)",
    )
    parser.add_argument(
        "--require-directories",
        action="store_true",
        help="promote directory and badge failures from warnings to blocking failures",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("distribution-results"),
        help="directory for distribution.json and summary.md",
    )
    return parser


def main(argv: list[str] | None = None, *, fetcher: Fetcher | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    if not arguments.online:
        parser.error("--online is required because this command queries public endpoints")

    try:
        expected_version = arguments.version or _project_version()
        client = fetcher or make_default_fetcher(os.environ.get("GITHUB_TOKEN"))
        report = verify_distribution(
            client,
            expected_version=expected_version,
            require_directories=arguments.require_directories,
        )
        write_evidence(report, arguments.out)
    except (DistributionError, OSError) as exc:
        print(f"distribution: {exc}", file=sys.stderr)
        return 2

    summary = report.as_dict()["summary"]
    assert isinstance(summary, dict)
    print(
        f"distribution: {report.status} "
        f"({summary['passed']} passed, {summary['warnings']} warnings, "
        f"{summary['failed']} failed)"
    )
    return 1 if report.status == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
