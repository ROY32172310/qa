from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ego_webqa import __version__

ROOT = Path(__file__).resolve().parents[1]
SERVER_NAME = "io.github.ROY32172310/qa"


def _server() -> dict[str, Any]:
    payload = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _project_version() -> str:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version = "([^"]+)"$', pyproject)
    assert match is not None
    return match.group(1)


def test_mcp_registry_metadata_matches_the_release_package() -> None:
    server = _server()
    version = _project_version()
    assert __version__ == version
    assert server["$schema"].endswith("/2025-12-11/server.schema.json")
    assert server["name"] == SERVER_NAME
    assert server["version"] == version
    assert len(server["description"]) <= 100
    assert server["websiteUrl"].startswith("https://")
    assert server["repository"] == {
        "url": "https://github.com/ROY32172310/qa",
        "source": "github",
        "id": "1436487315",
    }

    packages = server["packages"]
    assert len(packages) == 1
    package = packages[0]
    assert package["registryType"] == "pypi"
    assert package["registryBaseUrl"] == "https://pypi.org"
    assert package["identifier"] == "ego-webqa"
    assert package["version"] == version
    assert package["runtimeHint"] == "uvx"
    assert package["packageArguments"] == [{"type": "positional", "value": "mcp"}]
    assert package["transport"] == {"type": "stdio"}


def test_pypi_readme_contains_the_registry_ownership_marker() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"<!-- mcp-name: {SERVER_NAME} -->" in readme
    assert f"uvx ego-webqa@{_project_version()} mcp" in readme
