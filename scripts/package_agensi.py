#!/usr/bin/env python3
"""Build the deterministic Agensi marketplace ZIP."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import stat
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "integrations" / "agensi" / "web-delivery-qa-gate"
DEFAULT_OUTPUT = ROOT / "dist" / "agensi" / "web-delivery-qa-gate.zip"
ARCHIVE_ROOT = "web-delivery-qa-gate"
REQUIRED_FILES = {
    "SKILL.md",
    "SETUP.md",
    "mcp-config.example.json",
    "examples/expected-agent-summary.json",
    "examples/mcp-request.json",
    "examples/mobile-checkout-walkthrough.md",
    "references/report-contract.md",
}


def _project_version() -> str:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version = "([^"]+)"$', pyproject)
    if match is None:
        raise RuntimeError("pyproject.toml must declare a project version")
    return match.group(1)


def _package_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(SOURCE.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"Agensi package must not contain symlinks: {path}")
        if path.is_file():
            relative = path.relative_to(SOURCE)
            if any(part.startswith(".") or part == "__pycache__" for part in relative.parts):
                continue
            files.append(path)
    return files


def _validate_source(files: list[Path]) -> None:
    relative_files = {path.relative_to(SOURCE).as_posix() for path in files}
    missing = sorted(REQUIRED_FILES - relative_files)
    if missing:
        raise RuntimeError(f"Agensi package is missing required files: {', '.join(missing)}")

    config_path = SOURCE / "mcp-config.example.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    args = config["mcpServers"]["ego-webqa"]["args"]
    expected_package = f"ego-webqa=={_project_version()}"
    if args != ["--from", expected_package, "ego-webqa", "mcp"]:
        raise RuntimeError("Agensi MCP config must pin the current ego-webqa version")


def build_archive() -> tuple[bytes, list[str]]:
    """Return a reproducible ZIP and its member names."""

    files = _package_files()
    _validate_source(files)
    members: list[str] = []
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(SOURCE).as_posix()
            member = f"{ARCHIVE_ROOT}/{relative}"
            members.append(member)
            info = ZipInfo(member, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, path.read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9)
    return buffer.getvalue(), members


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify that the existing output is the current deterministic archive",
    )
    arguments = parser.parse_args(argv)

    try:
        payload, members = build_archive()
    except (KeyError, OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"agensi-package: {exc}", file=sys.stderr)
        return 2

    digest = hashlib.sha256(payload).hexdigest()
    output = arguments.out.resolve()
    if arguments.check:
        if not output.is_file() or output.read_bytes() != payload:
            print(f"agensi-package: stale or missing archive: {output}", file=sys.stderr)
            return 1
        print(f"{output} sha256={digest} files={len(members)}")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(f"{output} sha256={digest} files={len(members)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
