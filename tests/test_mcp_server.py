from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

pytest.importorskip("mcp", reason="mcp is not installed")

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from ego_webqa.contracts import load_schema
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
    (root / "flow.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport"
content="width=device-width"><title>MCP flow fixture</title><style>
body{margin:0;font:16px/1.5 system-ui}main{padding:32px}
button{min-height:48px;font-size:16px}[hidden]{display:none!important}
</style></head><body><main><h1>Agent flow gate</h1>
<button id="continue" onclick="document.querySelector('#success').hidden=false">
Continue</button><p id="success" hidden>Complete</p>
</main></body></html>""",
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
    assert "browser_engine" in schema["properties"]
    assert "viewport_preset" in schema["properties"]
    assert "smoke_flow_name" in schema["properties"]


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
    assert payload["agent_summary"]["status"] == "pass"
    assert payload["agent_summary"]["failed_items"] == []
    assert payload["screenshots"] == ["screenshots/mobile.png"]
    assert payload["artifacts"]["json"] == str(artifact_dir / "report.json")
    assert (artifact_dir / "agent_summary.json").is_file()
    Draft202012Validator(load_schema("report")).validate(payload)
    Draft202012Validator(load_schema("agent-summary")).validate(payload["agent_summary"])
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
    assert broken.structured_content["agent_summary"]["failed_items"][0]["dimension_id"]
    assert "horizontal_overflow" in {issue["code"] for issue in broken.structured_content["issues"]}


def test_mcp_tool_applies_quick_preset_and_rejects_ambiguous_matrix(
    site: tuple[LocalServer, Path],
    tmp_path: Path,
) -> None:
    server, _ = site
    result = audit_web_page(
        url=server.url("index.html"),
        out_dir=str(tmp_path / "quick"),
        viewport_preset="quick",
        smoke=False,
    )
    assert result.is_error is False
    payload = result.structured_content
    assert len(payload["viewports"]) == 4
    assert {row["viewport"]["width"] for row in payload["viewports"]} == {360, 390}

    conflicting = audit_web_page(
        url=server.url("index.html"),
        out_dir=str(tmp_path / "conflict"),
        viewport_preset="quick",
        viewports=["390x844:mobile"],
    )
    assert conflicting.is_error is True
    assert "not both" in conflicting.content[0].text


def test_mcp_tool_validates_target_and_accepts_local_directory(
    site: tuple[LocalServer, Path],
    tmp_path: Path,
) -> None:
    server, root = site
    config_path = tmp_path / "webqa.json"
    config_path.write_text("{}", encoding="utf-8")
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
        config=str(config_path),
        out_dir=str(tmp_path / "local"),
        viewports=["390x844:mobile"],
        smoke=False,
    )
    assert local.structured_content["status"] == "pass"
    source = local.structured_content["settings"]["source"]
    assert source["kind"] == "directory"
    assert source["directory"] == str(root.resolve())
    assert source["file"] == "index.html"
    assert source["config"] == str(config_path.resolve())


def test_mcp_tool_applies_governed_config_and_reports_audit_metadata(
    site: tuple[LocalServer, Path],
    tmp_path: Path,
) -> None:
    server, _ = site
    config_path = tmp_path / "governed.json"
    config_path.write_text(
        json.dumps(
            {
                "overrides": [
                    {
                        "dimension_id": "horizontal_overflow",
                        "reason": "Legacy dashboard migration",
                        "owner": "dashboard",
                        "expires": "2999-12-31",
                        "severity": "warn",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = audit_web_page(
        url=server.url("broken.html"),
        config=str(config_path),
        out_dir=str(tmp_path / "governed"),
        viewports=["390x844:mobile"],
        smoke=False,
    )

    payload = result.structured_content
    assert result.is_error is False
    assert payload["status"] == "warn"
    assert payload["issues"][0]["severity_source"] == "override"
    assert payload["governance"]["active_overrides"][0]["owner"] == "dashboard"
    assert payload["agent_summary"]["summary"]["overridden_dimensions"] == 1
    assert payload["agent_summary"]["summary"]["downgraded_blocks"] == 1


def test_mcp_tool_rejects_an_unregistered_browser_engine(tmp_path: Path) -> None:
    result = audit_web_page(
        url="https://example.com",
        out_dir=str(tmp_path / "invalid-engine"),
        browser_engine="safari",
    )
    assert result.is_error is True
    assert "browser_engine" in json.dumps(result.structured_content)


def test_mcp_tool_consumes_bounded_flow_from_config(
    site: tuple[LocalServer, Path],
    tmp_path: Path,
) -> None:
    _, root = site
    config_path = tmp_path / "flow.json"
    config_path.write_text(
        json.dumps(
            {
                "smoke_flow": [
                    {"action": "click", "selector": "#continue"},
                    {
                        "action": "expect_text",
                        "selector": "#success",
                        "pattern": "^complete$",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    result = audit_web_page(
        directory=str(root),
        file="flow.html",
        config=str(config_path),
        out_dir=str(tmp_path / "flow"),
        viewports=["390x844:mobile"],
        smoke=True,
    )
    assert result.is_error is False
    assert result.structured_content["smoke"]["kind"] == "flow"
    assert result.structured_content["smoke"]["success"] is True
    assert result.structured_content["smoke"]["assertions"][0]["type"] == "text"


def test_mcp_tool_selects_named_flow_from_config(
    site: tuple[LocalServer, Path],
    tmp_path: Path,
) -> None:
    _, root = site
    config_path = tmp_path / "named-flows.json"
    config_path.write_text(
        json.dumps(
            {
                "smoke_flows": {
                    "default": [
                        {"action": "click", "selector": "#continue"},
                        {
                            "action": "expect_text",
                            "selector": "#success",
                            "pattern": "^complete$",
                        },
                    ],
                    "visible-only": [
                        {"action": "click", "selector": "#continue"},
                        {"action": "expect_visible", "selector": "#success"},
                    ],
                },
                "smoke_flow_name": "default",
            }
        ),
        encoding="utf-8",
    )
    result = audit_web_page(
        directory=str(root),
        file="flow.html",
        config=str(config_path),
        out_dir=str(tmp_path / "named-flow"),
        viewports=["390x844:mobile"],
        smoke=True,
        smoke_flow_name="visible-only",
    )
    assert result.is_error is False
    assert result.structured_content["smoke"]["flow_name"] == "visible-only"
    assert result.structured_content["smoke"]["success"] is True


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
    Draft202012Validator(load_schema("report")).validate(payload)
    Draft202012Validator(load_schema("agent-summary")).validate(payload["agent_summary"])
    assert (tmp_path / "stdio" / "report.json").is_file()
