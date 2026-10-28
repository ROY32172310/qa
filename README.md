# ego-webqa

Deterministic coarse delivery QA for AI-generated web pages, H5 demos, and PWAs.

Point it at a URL. It opens the page in a real Chromium browser, checks a
mobile/tablet/desktop matrix, safely probes the primary call to action, and
leaves screenshots plus machine-readable evidence behind.

## Why

Generated pages often pass unit tests while still shipping obvious delivery
defects: content wider than the phone, invisible buttons, broken images,
console errors, a call-to-action that does nothing, or a page that shifts while
the user is trying to tap it.

`ego-webqa` turns those into deterministic checks. It is not a visual-regression
service and does not require writing tests or storing approved screenshots.

## Install

Install the published package from PyPI:

```bash
python -m pip install ego-webqa
python -m playwright install chromium
```

To install the current checkout before a release:

```bash
git clone https://github.com/ROY32172310/qa.git
cd qa
python -m pip install .
python -m playwright install chromium
```

For development, use `python -m pip install -e '.[dev]'`.

Use a system Chrome instead of downloading Chromium:

```bash
ego-webqa https://example.com --browser-channel chrome
```

## Use

```bash
ego-webqa https://example.com
ego-webqa --dir ./dist --file index.html
ego-webqa http://127.0.0.1:8000 --viewports 390x844,768x1024,1440x900
ego-webqa https://example.com --ready-selector "#app-ready" --wait-for-network-idle
ego-webqa https://example.com --smoke-success-selector "#thank-you"
ego-webqa https://example.com --smoke-scope all --smoke-require-assertion \
  --smoke-success-selector "#thank-you"
ego-webqa https://example.com --profile accessibility
```

Exit codes:

- `0`: pass or warnings only
- `1`: at least one blocking error
- `2`: invalid invocation or browser/runtime failure

Every run writes self-contained evidence. Screenshot references in JSON are
relative to the report directory, so agents and CI can move the complete
artifact directory without rewriting paths:

```text
webqa-report/
├── report.json
├── agent_summary.json
├── junit.xml
├── report.sarif
└── screenshots/
```

Add `--fail-on-warn` for CI gates that require a completely clean report.

`agent_summary.json` is the compact Agent-facing view. Repeated findings are
aggregated by registered dimension, so the same root cause across several
viewports produces one repair item with affected triggers and a reproducible
command. MCP callers receive the same summary as structured content and as the
short text result.

Each repair item keeps the first evidence object for compatibility and an
`evidence_by_viewport` map for the complete cross-viewport evidence. Network
failures additionally carry `failure_details` with resource type, frame URL,
same-origin status, redirect source, HTTP status or browser error, and occurrence
count. Query strings and credentials are removed from all reported URLs.

## Checks

Blocking errors:

- horizontal page overflow
- JavaScript page errors and `console.error`
- failed resources and HTTP errors
- a nearly blank page
- unreadable text below 10px
- broken visible images
- distorted canvas/image/video aspect ratio
- dead primary CTA
- severe unexpected layout shift

Warnings:

- DOM rendered, but the `load` event exceeded its bounded deadline
- small hit targets below 44px
- secondary text below 12px
- oversized fixed overlays
- slow first contentful paint
- moderate layout shift
- excessive first-load bytes or request count

The browser probe reports facts. All thresholds and pass/fail decisions live in
[`src/ego_webqa/config.py`](src/ego_webqa/config.py).
The aspect-ratio check only evaluates rendered media at least
`aspect_min_rendered_px` (48px by default), avoiding pixel-rounding noise from
small icons.

### Dimensions

Issue codes belong to a closed, versioned registry in
[`src/ego_webqa/dimensions.py`](src/ego_webqa/dimensions.py). Reports reject an
unregistered code, and each Agent summary item carries the dimension id,
version, detector, and default severity. Docs and integrations can inspect the
same source of truth without parsing prose:

```bash
ego-webqa --list-dimensions
```

### Profiles

`baseline` is the default delivery profile. It checks whether the page renders,
responds, fits the viewport, and lets the primary action work.

`accessibility` keeps every baseline check and adds deterministic checks for:

- missing document language or page title
- controls without an accessible name
- visible images without an `alt` attribute
- interactive content inside `aria-hidden` containers
- duplicate IDs and skipped heading levels
- positive `tabindex` values that override the natural focus order

This profile catches common machine-detectable defects. It is not a WCAG
conformance audit or a replacement for keyboard and assistive-technology
testing.

## Configuration

```bash
ego-webqa https://example.com --config examples/webqa.json
```

```json
{
  "profile": "accessibility",
  "viewports": ["390x844:mobile", "768x1024:tablet", "1280x800:desktop"],
  "min_tap_target_px": 44,
  "min_font_px": 12,
  "ready_selector": "#app-ready",
  "wait_for_network_idle": true,
  "smoke_mode": "safe",
  "smoke_scope": "all",
  "smoke_settle_ms": 800,
  "smoke_require_assertion": true,
  "smoke_success_selector": "#thank-you",
  "smoke_success_url_pattern": "/complete$",
  "ignore_selectors": [".third-party-chat-widget"],
  "ignore_console_patterns": ["third-party-widget"],
  "ignore_request_patterns": ["/analytics/"]
}
```

Use `--smoke-selector "#checkout"` when the primary action's text is not matched
by the default CTA vocabulary. Safe smoke aborts HTTP requests and switches the
isolated browser context offline after the initial load. Use `--smoke-mode live`
only when real side effects are intended, or `--no-smoke` when even a DOM-only
click is undesirable.

`smoke_success_selector` and `smoke_success_url_pattern` replace the generic
"something changed" heuristic with an explicit post-click contract. When both
are configured, both must change from unmatched to matched.

Set `smoke_scope` to `all` to exercise the CTA independently in every viewport.
Use `smoke_require_assertion` for delivery gates that must not accept a vague
DOM change as success.

Use `ready_selector` for SPA content that appears after the load event. Known
third-party console and request noise can be excluded with regex patterns
without hiding DOM-based findings. Ignored responses are excluded from both
request counts and transfer-byte budgets. Reports record whether ready content,
fonts, and bounded network idle were reached.

### Authenticated previews

Previews behind HTTP Basic auth, request headers, or a signed-in browser session
are supported through JSON configuration or environment variables:

```bash
export EGO_WEBQA_HTTP_USERNAME=preview-user
export EGO_WEBQA_HTTP_PASSWORD=preview-password
export EGO_WEBQA_EXTRA_HTTP_HEADERS='{"X-Preview-Key":"agent-key"}'
ego-webqa "$PREVIEW_URL" --storage-state ./auth/storage-state.json
```

Credentials and header values are redacted from the JSON report. Passing them
through environment variables also keeps them out of the CLI process argument
list.

## Platforms and multi-agent use

The audit engine runs on Linux, macOS, and Windows with Python 3.10 or newer.
CI exercises the same test suite on all three operating systems.

Every `audit()` or CLI invocation owns its browser lifecycle, browser contexts,
static local server, and output directory. There is no shared mutable audit
state, so multiple agents can run concurrently when each supplies a unique
`--out` directory:

```bash
ego-webqa "$PREVIEW_URL" --out "webqa/$AGENT_ID" --json \
  --smoke-scope all --smoke-require-assertion \
  --smoke-success-selector "#thank-you"
```

`--json` prints the same stable payload written to `report.json`.
`schema_version` governs compatibility; JUnit and SARIF are derived from the
same in-memory issue list. Agents should treat exit code `0` as pass/warn, `1`
as blocking findings, and `2` as an invocation or browser failure.

Within one audit, up to three viewports render in isolated browsers
concurrently. This bounds slow-site wall time without sharing cookies, network
state, screenshots, or mutable evidence between viewports.

### MCP server

Install the optional MCP adapter and expose the gate directly inside an AI
coding agent:

```bash
python -m pip install 'ego-webqa[mcp]'
python -m playwright install chromium
ego-webqa-mcp
```

An MCP client launches the command over stdio. The server advertises one tool,
`audit_web_page`, with structured success and blocking-error results:

```json
{
  "mcpServers": {
    "ego-webqa": {
      "command": "ego-webqa-mcp",
      "args": []
    }
  }
}
```

Typical tool arguments are:

```json
{
  "url": "http://127.0.0.1:5173",
  "out_dir": ".qa/agent-a",
  "profile": "accessibility",
  "viewports": ["390x844:mobile", "1280x800:desktop"],
  "smoke_scope": "all",
  "smoke_require_assertion": true,
  "smoke_success_selector": "#thank-you"
}
```

The MCP result is marked as an error when the report status is `fail`, while
the full report remains available as structured content. Authentication
environment variables are read by the server process, not passed as tool
arguments. This adapter deliberately remains a delivery-usability gate; it is
not a security scanner, WCAG certification tool, or visual-regression system.

## GitHub Actions

This repository is also a composite GitHub Action. The Action installs the
package from the Action ref, installs Chromium, runs the audit, and uploads the
report even when the audit fails:

```yaml
jobs:
  delivery-qa:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: ROY32172310/qa@v0.2.3
        with:
          url: ${{ vars.PREVIEW_URL }}
          profile: accessibility
          fail-on-warn: "true"
          smoke-scope: all
          smoke-require-assertion: "true"
          smoke-success-selector: "#thank-you"
          http-username: ${{ secrets.PREVIEW_USERNAME }}
          http-password: ${{ secrets.PREVIEW_PASSWORD }}
          extra-http-headers: ${{ secrets.PREVIEW_HEADERS_JSON }}
          artifact-name: webqa-${{ github.run_id }}
```

For a local checkout of this repository, use `uses: ./` after checkout. The
Action's `safe` smoke mode is the default; set `smoke-mode: live` only when the
click is intentionally allowed to cause real side effects. See
[`examples/github-action.yml`](examples/github-action.yml) and
[`action.yml`](action.yml) for the full input set. The `@v0.2.3` tag is created
only after the same commit passes the full cross-platform CI matrix.

## Python API

```python
from ego_webqa import Settings, audit

report = audit("https://example.com", settings=Settings(), output_dir="qa")
print(report.status)
```

## Scope and independence

This is a deterministic coarse gate for obvious delivery failures. It does not
prove that a business flow works, that every supported browser matches, or that
the page is secure.

Fixed report scope:

> 本报告仅覆盖多终端几何与基础体验的确定性粗检；业务主路径、跨浏览器兼容、安全合规需另行验证。

This repository is a standalone extraction of the general-purpose delivery
checks originally proven inside the ego project. It has no dependency on
`ego_protocol`, `ego_uri`, ego sharing, deployment, miniapp, or product-shell
semantics. Product-specific checks belong in plugins, not in the core.

## Development

```bash
python -m pip install -e '.[dev]'
python -m playwright install chromium
pytest
ruff check .
black --check .
mypy
```

See [CONTRIBUTING.md](CONTRIBUTING.md) before adding a rule. Every rule needs a
positive control and an observed failure mode.

## License

MIT
