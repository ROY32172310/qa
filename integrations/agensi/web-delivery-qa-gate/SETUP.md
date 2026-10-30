# Local MCP setup

This package uses the buyer's local `ego-webqa` installation. Agensi does not
host or execute the MCP server.

## 1. Install Python, uv, and Chromium

Use Python 3.10 or newer. `uv` provides `uvx`, which runs the pinned package in
an isolated environment.

```bash
uvx --from ego-webqa==0.8.0 ego-webqa install-browser
uvx --from ego-webqa==0.8.0 ego-webqa doctor --json
```

Run `doctor` again after browser installation. It must report that Python, the
MCP dependency, Playwright, the browser executable, and a real headless launch
are available. The package pins its Playwright dependency so separate `uvx`
runs select the same browser revision. A browser-install failure is an
environment problem, not evidence about the page being audited.

## 2. Add the MCP server to the local agent

`mcp-config.example.json` uses the common `mcpServers` shape:

```json
{
  "mcpServers": {
    "ego-webqa": {
      "command": "uvx",
      "args": ["--from", "ego-webqa==0.8.0", "ego-webqa", "mcp"]
    }
  }
}
```

Agent products differ in where this block belongs. Copy the `ego-webqa` server
entry into the buyer's existing MCP configuration and preserve that product's
outer key or file format. On Windows, use `uvx.exe` if the client does not
resolve `uvx` through `PATH`.

If `ego-webqa` is installed directly, the equivalent local command is:

```json
{
  "command": "ego-webqa",
  "args": ["mcp"]
}
```

Restart the agent after changing its configuration. It should expose one tool,
`audit_web_page`.

## 3. Verify through the agent

Ask the agent:

```text
Audit https://example.com with the installed ego-webqa tool and summarize
blocking findings before treating the page as delivered.
```

An `is_error` tool result can mean either a blocking page-quality finding or an
execution failure. Read the structured summary: a page finding contains a
dimension, selector, trigger, problem, and repair direction. An execution error
means Python, the browser, or the MCP process could not complete.

## 4. Use the CLI as a fallback

The Skill also documents direct CLI commands. The shortest check is:

```bash
uvx --from ego-webqa==0.8.0 ego-webqa "https://example.com" \
  --out .qa/agent-delivery --json
```

Exit `0` means no blocking finding. Exit `1` means at least one blocking
finding. Exit `2` means the audit could not run reliably.

## Boundary

This setup installs a local coarse web-delivery check. It does not provide a
hosted audit service, security review, WCAG certification, visual regression,
or a general end-to-end testing platform.
