"""Model Context Protocol adapter for agent-native delivery gates."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from mcp import types
from mcp.server.mcpserver import MCPServer

from . import __version__
from .config import Settings, Viewport, apply_auth_environment, load_settings
from .engine import AuditRuntimeError, audit
from .reporting import build_agent_summary, write_reports
from .server import LocalServer

TOOL_NAME = "audit_web_page"


def _result(payload: dict[str, Any], *, is_error: bool) -> types.CallToolResult:
    summary = payload.get("agent_summary") or {
        "status": payload.get("status"),
        "counts": payload.get("counts"),
    }
    return types.CallToolResult(
        content=[
            types.TextContent(
                type="text",
                text=json.dumps(summary, ensure_ascii=False, separators=(",", ":")),
            )
        ],
        structured_content=payload,
        is_error=is_error,
    )


def _error_result(message: str) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=message)],
        structured_content={"status": "error", "error": message},
        is_error=True,
    )


def audit_web_page(
    url: str = "",
    directory: str = "",
    file: str = "index.html",
    out_dir: str = "",
    config: str = "",
    profile: str = "baseline",
    viewports: list[str] | None = None,
    viewport_preset: str = "",
    timeout_ms: int | None = None,
    ready_selector: str = "",
    wait_for_network_idle: bool = False,
    smoke: bool = True,
    smoke_scope: str = "first",
    smoke_settle_ms: int | None = None,
    smoke_selector: str = "",
    smoke_success_selector: str = "",
    smoke_success_url_pattern: str = "",
    smoke_require_assertion: bool = False,
    smoke_flow_name: str = "",
    browser_engine: str = "",
) -> types.CallToolResult:
    """Audit a generated page in a real browser and return deterministic evidence.

    Provide exactly one of `url` or `directory`. The result is blocked when the
    page has a delivery error; warnings remain visible but do not block unless
    `fail_on_warn` is enabled in the JSON config. This checks delivery usability,
    not security, WCAG conformance, visual regression, or real-device Safari
    parity. Use browser_engine="webkit" for a WebKit approximation only.
    """

    if bool(url) == bool(directory):
        return _error_result("provide exactly one of url or directory")
    if viewports and viewport_preset:
        return _error_result("provide either viewports or viewport_preset, not both")
    try:
        cfg = load_settings(config) if config else Settings()
        updates: dict[str, Any] = {
            "profile": profile,
            "ready_selector": ready_selector,
            "wait_for_network_idle": wait_for_network_idle,
            "smoke_scope": smoke_scope,
            "smoke_selector": smoke_selector,
            "smoke_success_selector": smoke_success_selector,
            "smoke_success_url_pattern": smoke_success_url_pattern,
            "smoke_require_assertion": smoke_require_assertion,
        }
        if smoke_flow_name:
            updates["smoke_flow_name"] = smoke_flow_name
        if viewport_preset:
            updates["viewport_preset"] = viewport_preset
        if viewports:
            updates["viewports"] = [Viewport.parse(item) for item in viewports]
        if timeout_ms is not None:
            updates["timeout_ms"] = timeout_ms
        if smoke_settle_ms is not None:
            updates["smoke_settle_ms"] = smoke_settle_ms
        if browser_engine:
            updates["browser_engine"] = browser_engine
        cfg = apply_auth_environment(Settings.from_mapping(updates, base=cfg))

        output = (
            Path(out_dir)
            if out_dir
            else Path.cwd() / "webqa-mcp" / f"{__version__}-{uuid.uuid4().hex}"
        )
        local_server: LocalServer | None = None
        target = url
        try:
            if directory:
                local_server = LocalServer(directory)
                target = local_server.url(file)
            report = audit(target, settings=cfg, output_dir=output, smoke=smoke)
            source: dict[str, str] = {"kind": "url"}
            if directory:
                source = {
                    "kind": "directory",
                    "directory": str(Path(directory).resolve()),
                    "file": file,
                }
            if config:
                source["config"] = str(Path(config).resolve())
            report.settings["source"] = source
            artifacts = write_reports(report, output)
        finally:
            if local_server is not None:
                local_server.close()
    except (AuditRuntimeError, OSError, ValueError) as exc:
        return _error_result(str(exc))

    payload = report.to_dict()
    payload["agent_summary"] = build_agent_summary(report)
    payload["artifacts"] = artifacts
    payload["output_dir"] = str(output.resolve())
    return _result(payload, is_error=report.status == "fail")


def build_server() -> MCPServer[dict[str, Any]]:
    """Build the stdio MCP server exposed by the `ego-webqa-mcp` command."""

    server: MCPServer[dict[str, Any]] = MCPServer(
        name="ego-webqa",
        title="ego-webqa delivery gate",
        description="Deterministic browser delivery checks for AI-generated pages.",
        instructions=(
            "Call audit_web_page after generating or changing a web page. Treat an "
            "isError result as a blocking delivery failure and use the structured "
            "issues as repair evidence. This tool checks delivery usability, not "
            "security, WCAG conformance, or visual regression."
        ),
        version=__version__,
    )
    server.add_tool(
        audit_web_page,
        name=TOOL_NAME,
        title="Audit generated web page",
        structured_output=False,
    )
    return server


def main() -> None:
    """Run the MCP server over stdio."""

    asyncio.run(build_server().run_stdio_async())


if __name__ == "__main__":
    main()
