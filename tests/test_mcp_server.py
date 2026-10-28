from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="mcp is not installed")

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from ego_webqa.mcp_server import TOOL_NAME, audit_web_page, build_server
from ego_webqa.server import LocalServer

ROOT = Path(__file__).resolve().parents[1]

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        not importlib.util.find_spec("playwright"), reason="playwright is not installed"
    ),
]


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> tuple[LocalServer, Path]:
    root = tmp_path_factory.mktemp("mcp-site")
    (root / "index.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport"
content="width=device-width"><title>MCP fixture</title><style>
body{margin:0;font:16px/1.5 system-ui}main{padding:32px}</style></head>
<body><main><h1>Agent delivery gate</h1><p>This page is ready to ship.</p>
</main></body></html>""",
        encoding="utf-8",
    )
    (root / "broken.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport"
content="width=device-width"><title>Broken MCP fixture</title><style>
body{margin:0;font:16px/1.5 system-ui}.wide{width:2400px;height:20px}
</style></head><body><main><h1>Broken page</h1><p>Overflow is intentional.</p>
<div class="wide">overflow</div></main></body></html>""",
        encoding="utf-8",
    )
    server = LocalServer(root)
    yield server, root
    server.close()


def test_mcp_server_exposes_one_scoped_tool() -> None:
    tools = asyncio.run(build_server().list_tools())
    assert [tool.name for tool in tools] == [TOOL_NAME]
    assert "security" in (tools[0].description or "")
    assert "WCAG" in (tools[0].description or "")
    schema = tools[0].input_schema
    assert schema["type"] == "object"
    assert "url" in schema["properties"]
    assert "directory" in schema["properties"]


def test_mcp_tool_returns_blocking_evidence(
    site: tuple[LocalServer, Path],
    tmp_path: Path,
) -> None:
    server, _ = site
    result = audit_web_page(
        url=server.url("index.html"),
        out_dir=str(tmp_path / "pass"),
        viewports=["390x844:mobile"],
        smoke=False,
    )
    artifact_dir = tmp_path / "pass"
    assert (artifact_dir / "report.json").is_file()
    assert (artifact_dir / "screenshots" / "mobile.png").is_file()
    payload = result.structured_content
    assert payload["status"] == "pass"
    assert payload["counts"] == {"error": 0, "warning": 0}
    assert payload["screenshots"] == ["screenshots/mobile.png"]
    assert payload["artifacts"]["json"] == str(artifact_dir / "report.json")
    summary = json.loads(result.content[0].text)
    assert summary["status"] == "pass"

    broken = audit_web_page(
        url=server.url("broken.html"),
        out_dir=str(tmp_path / "broken"),
        viewports=["390x844:mobile"],
        smoke=False,
    )
    assert broken.is_error is True
    assert broken.structured_content["status"] == "fail"
    assert "horizontal_overflow" in {issue["code"] for issue in broken.structured_content["issues"]}


def test_mcp_tool_validates_target_and_accepts_local_directory(
    site: tuple[LocalServer, Path],
    tmp_path: Path,
) -> None:
    server, root = site
    missing = audit_web_page(out_dir=str(tmp_path / "missing"))
    assert missing.is_error is True
    assert missing.structured_content["status"] == "error"

    both = audit_web_page(
        url=server.url("index.html"),
        directory=str(root),
        out_dir=str(tmp_path / "both"),
    )
    assert both.is_error is True

    local = audit_web_page(
        directory=str(root),
        out_dir=str(tmp_path / "local"),
        viewports=["390x844:mobile"],
        smoke=False,
    )
    assert local.structured_content["status"] == "pass"


def test_mcp_stdio_round_trip(site: tuple[LocalServer, Path], tmp_path: Path) -> None:
    server, _ = site

    async def scenario() -> tuple[list[str], dict[str, object]]:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "ego_webqa.mcp_server"],
            cwd=ROOT,
            env={"PYTHONPATH": str(ROOT / "src")},
        )
        async with (
            stdio_client(parameters) as (read_stream, write_stream),
            ClientSession(read_stream, write_stream) as session,
        ):
            initialized = await session.initialize()
            assert initialized.server_info.name == "ego-webqa"
            listed = await session.list_tools()
            called = await session.call_tool(
                TOOL_NAME,
                {
                    "url": server.url("index.html"),
                    "out_dir": str(tmp_path / "stdio"),
                    "viewports": ["390x844:mobile"],
                    "smoke": False,
                },
            )
            assert called.is_error is False
            return [tool.name for tool in listed.tools], called.structured_content

    tool_names, payload = asyncio.run(scenario())
    assert tool_names == [TOOL_NAME]
    assert payload["status"] == "pass"
    assert (tmp_path / "stdio" / "report.json").is_file()
