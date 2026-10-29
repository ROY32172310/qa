# DeepSeek Harness integration

## Decision

The Python browser audit remains the only implementation of the checks.
DeepSeek Harness (`dsh`) consumes it through DSH's native MCP client, packaged
as a separate declarative bundle named `dsh-ego-webqa`. The bundle does not
reimplement the tool or invoke the CLI directly.

The integration sequence is:

1. The CLI and MCP interfaces remain authoritative.
2. A separate `dsh-ego-webqa` npm package contributes one Cordis patch row:
   `@deepseek-ai/dsh-mcp-client` launched with
   `uvx ego-webqa@<tested-version> mcp`.
3. DSH supervises the stdio MCP process, discovers the existing
   `audit_web_page` tool, and exposes it as
   `mcp__ego_webqa__audit_web_page`.
4. The npm package declares the tested DSH runtime range and pins a compatible
   `ego-webqa` version. Operators can override the generated profile row to use
   a locally installed CLI.

## Why separate

- DSH is a Cordis/npm process with a developer-preview compatibility window;
  the QA core is Python/Playwright with a separate cross-platform release
  matrix.
- DSH already owns MCP process supervision, reconnect, cancellation, approval,
  and stable namespace-qualified tool names. Rebuilding that as a custom
  subprocess tool would add code without improving the product contract.
- Keeping the adapter separate prevents a DSH API break from blocking core
  fixes and prevents a QA packaging change from forcing a DSH runtime bump.
- The adapter can be listed in a DSH plugin index independently while the
  Python package remains listed in PyPI and the official MCP Registry.

## Contract

The adapter must preserve these boundaries:

- one bounded `audit_web_page` call per MCP invocation;
- argv-only process launch through DSH and `uvx`, never shell construction from
  model-provided values;
- no secrets in command arguments or returned evidence;
- no arbitrary detector code;
- DSH bridges the existing MCP result; it does not reinterpret raw browser
  state or define a second report schema;
- network and browser failures return a structured error that distinguishes
  execution failure from a page delivery failure.

The bundle should not expose individual checks as separate tools. A single
audit result is the product contract, and extra tools would fragment repair
evidence and create needless model round trips.

## Acceptance criteria

- `dsh --dump-config` shows one `@deepseek-ai/dsh-mcp-client` row with a unique
  `ego_webqa` namespace.
- The discovered tool is named `mcp__ego_webqa__audit_web_page`.
- A clean page returns a successful structured MCP result.
- A page with a blocking defect returns a valid `fail` report rather than an
  execution error.
- Missing `uvx`, an unavailable pinned package, or missing Chromium fails
  visibly; it never appears as a passing page audit.
- Uninstall removes both the bundle layer and the supervised MCP process.

## Current status

MCP is the portable integration implemented in this repository. The standalone
declarative DSH bundle is maintained separately so this Python release can keep
a stable machine contract and avoid a second QA implementation.
