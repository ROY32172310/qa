[![Indexed on TensorBlock MCP Index](https://mcp-index.tensorblock.co/v1/servers/github-roy32172310-qa-73ad3a11/badge.svg)](https://www.tensorblock.co/mcp/servers/github-roy32172310-qa-73ad3a11)

<a href="https://glama.ai/mcp/servers/ROY32172310/qa"><img src="https://glama.ai/mcp/servers/ROY32172310/qa/badge" alt="Glama MCP server: license A, quality A, maintenance A" width="380"></a>

# ego-webqa

<!-- mcp-name: io.github.ROY32172310/qa -->

[![PyPI](https://img.shields.io/pypi/v/ego-webqa.svg)](https://pypi.org/project/ego-webqa/)
[![CI](https://github.com/ROY32172310/qa/actions/workflows/ci.yml/badge.svg)](https://github.com/ROY32172310/qa/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/ego-webqa.svg)](https://pypi.org/project/ego-webqa/)
[![License](https://img.shields.io/pypi/l/ego-webqa.svg)](LICENSE)

Deterministic coarse delivery QA for AI-generated web pages, H5 demos, and PWAs.

Point it at a URL. It opens the page in a real Chromium browser by default,
checks a zero-config narrow-mobile matrix, safely probes the primary call to
action, and leaves screenshots plus machine-readable evidence behind. Firefox
and Playwright WebKit can be selected one engine at a time. The default eight
variants combine:

- 360px and 390px widths;
- 1.0x and 1.5x text scaling;
- 0px and 34px simulated bottom safe area.

## See the result in 30 seconds

Prefer to inspect a completed run first? Open the
[live before-and-after evidence board](https://roy32172310.github.io/qa/).

```bash
python -m pip install ego-webqa
ego-webqa setup
ego-webqa https://your-preview.example --out .qa/first
```

`setup` first checks the selected browser. If it already launches, setup exits
without downloading anything; otherwise it installs the pinned Playwright
headless shell with the active `ego-webqa` Python interpreter and verifies a
real headless launch. The first Chromium setup avoids the full headed browser
build because audits only run headless. Ordinary `doctor` and audit commands
never download a browser implicitly. The
audit command exits `0` for pass/warnings, `1` for blocking delivery defects,
and `2` for an audit or browser failure. Each run leaves screenshots and
structured evidence:

```text
.qa/first/
├── agent_summary.json   # one aggregated, repair-ready item per root cause
├── feedback_bundle.json # privacy-safe summary for external issue reports
├── report.json
├── junit.xml
├── report.sarif
└── screenshots/
```

A real dogfood finding looks like this:

```json
{
  "dimension_id": "text_scale_layout_break",
  "selector": "body > div:nth-of-type(2) > div:nth-of-type(2) > a",
  "text_snippet": "我也要创建 →",
  "problem": "page is 9px wider than the viewport at 1.5x text scale",
  "trigger": "mobile-360-150-safe0 (360x800); mobile-360-150-safe34 (360x800)",
  "severity": "block"
}
```

The report explains what broke, where it happened, which viewport combinations
were affected, and gives the Agent a command that reproduces the failure.

## What real pages exposed

The v0.8.0 dogfood pass audited all 20 Ego-owned production or canonical
generated pages with zero runtime errors. Ten pages were clean; the remaining
findings aggregated to 22 repair items. Stable failures included six
text-enlargement layout breaks, four bottom safe-area penetrations, five
clipped-text root causes, four undersized-target groups, and one generated page
loading a missing service worker. There are no known stable blocking false
positives in this corpus. This is a small, disclosed corpus rather than a
market-wide accuracy claim; the full evidence and limitations are in
[`docs/real-world-dogfood-2026-10-30-v0.8.0.md`](docs/real-world-dogfood-2026-10-30-v0.8.0.md).

Layout failures now identify the deepest unclipped elements that own the
overflow, so an Agent receives a concrete repair selector instead of `html`.

See how one generated page went from three root causes to zero blocking defects
in the
[vocabulary repair case study](docs/case-study-vocabulary-repair-2026-10-29.md).
If you want to test the same loop on one of your pages, follow the
[15-minute first-trial protocol](docs/first-trial.md).
The [field feedback protocol](docs/field-feedback.md) defines how real cases
are classified and converted into clean controls or benchmark fixtures.

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
ego-webqa setup
```

To install the current checkout before a release:

```bash
git clone https://github.com/ROY32172310/qa.git
cd qa
python -m pip install .
ego-webqa setup
```

For development, use the committed lockfile:

```bash
uv lock --check
uv sync --locked --all-extras
uv run --locked ego-webqa setup
```

Without `uv`, `python -m pip install -e '.[dev]'` remains supported.

If `uv` is available and you do not want a persistent Python package install,
use the same commands through an isolated, version-pinned `uvx` environment:

```bash
uvx --from ego-webqa==0.8.2 ego-webqa setup
uvx --from ego-webqa==0.8.2 ego-webqa https://your-preview.example
```

Playwright is pinned by the package, and browser binaries live in Playwright's
shared cache, so the temporary `uvx` environment and later MCP launches reuse
the same browser revision.

If `doctor` reports missing Linux system libraries, ask setup to install them:

```bash
ego-webqa setup --with-deps
```

Setup is intentionally a separate, explicit command: wheel installs remain
offline-safe, while browser downloads and operating system changes are visible,
retryable user actions. `setup` is idempotent and reuses a browser that already
passes a real launch check. Use `setup --dry-run` to inspect the exact
interpreter-bound command, or `--force` to reinstall a damaged browser revision.

For a lower-level repair or explicit installation command, use:

```bash
ego-webqa install-browser
ego-webqa doctor
```

Chromium installation is headless-only by default. If another tool on the same
machine requires the full headed Chromium build, opt in explicitly:

```bash
ego-webqa setup --full-chromium
```

Use a system Chrome instead of downloading Chromium:

```bash
ego-webqa https://example.com --browser-channel chrome
```

### Firefox and WebKit

Install only the additional engine you need, then select it for the whole audit:

```bash
ego-webqa setup --browser-engine firefox
ego-webqa https://example.com --browser-engine firefox

ego-webqa setup --browser-engine webkit
ego-webqa https://example.com --browser-engine webkit
```

Chromium remains the default. Each audit runs one engine; this does not silently
multiply browser cost or claim cross-engine parity. The `webkit` option uses
Playwright's WebKit build and supplies useful Safari-engine evidence, but it is
not a real iPhone, iPad, or macOS Safari run. Use real-device testing when the
delivery decision requires it.

## Use

```bash
ego-webqa https://example.com
ego-webqa --dir ./dist --file index.html
ego-webqa https://example.com --preset quick
ego-webqa http://127.0.0.1:8000 --viewports 390x844:mobile@1.5~34,1280x800:desktop
ego-webqa https://example.com --browser-engine firefox
ego-webqa https://example.com --ready-selector "#app-ready" --wait-for-network-idle
ego-webqa https://example.com --smoke-success-selector "#thank-you"
ego-webqa https://example.com --smoke-scope all --smoke-require-assertion \
  --smoke-success-selector "#thank-you"
ego-webqa --dir examples/demo --config examples/webqa-demo-flow.json
ego-webqa https://example.com --profile accessibility
```

Exit codes:

- `0`: pass or warnings only
- `1`: at least one blocking error
- `2`: invalid invocation or browser/runtime failure

`--viewports` accepts `WIDTHxHEIGHT[:NAME][@TEXT_SCALE][~SAFE_BOTTOM_PX]`.
Explicit viewports replace the default matrix. Text scale must be between 1.0
and 2.0; the simulated bottom safe area must be between 0 and 100px.

`--preset quick` selects four pairwise-balanced mobile variants for fast Agent
loops: each width covers both text scales and both safe-area states, while the
crossed scale/safe-area combinations alternate by width. `--preset full`
explicitly selects the default eight-variant matrix. A preset cannot be combined
with `--viewports`.

Every run writes self-contained evidence. Screenshot references in JSON are
relative to the report directory, so agents and CI can move the complete
artifact directory without rewriting paths:

```text
webqa-report/
├── report.json
├── agent_summary.json
├── feedback_bundle.json
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

`feedback_bundle.json` is the external-feedback view. By default it includes
dimension ids, counts, sanitized viewport geometry, browser engine, and target
type, but omits the target URL, local paths, custom viewport names, selectors,
page text, messages, raw evidence, screenshots, and configuration contents.
Review it before sharing. To deliberately add context for a private issue:

```bash
ego-webqa feedback --report webqa-report/report.json
ego-webqa feedback --report webqa-report/report.json \
  --include-target --include-selectors --include-messages \
  --out webqa-report/feedback-with-context.json
```

The first command regenerates the default bundle beside the report. The second
is an explicit opt-in and may contain page-sensitive data.

### Baseline and regression gate

Compare a run with a known-good report without maintaining screenshots. Stable
fingerprints combine the registered dimension with its selector or root cause:

```bash
ego-webqa https://your-preview.example \
  --out .qa/current \
  --baseline-report .qa/known-good/report.json \
  --gate new

ego-webqa delta \
  --baseline .qa/known-good/report.json \
  --current .qa/current/report.json
```

The run writes `delta.json` with `new`, `persistent`, `changed`, and `resolved`
root causes. `--gate new` fails only when a blocking root cause is new, becomes
blocking, increases its blocking occurrences, or affects an additional viewport.
Existing unresolved blockers remain visible but do not make an unchanged build
fail again. Add `--fail-on-warn` to gate new or changed warnings as well.

Both reports must use the same target source, profile, viewport matrix, browser
engine, and browser channel. Intentional cross-target or cross-configuration
comparisons require `--allow-target-change` and/or
`--allow-configuration-change`. This is a deterministic finding delta, not a
visual-regression baseline.

Each repair item keeps the first evidence object for compatibility and an
`evidence_by_viewport` map for the complete cross-viewport evidence. Network
failures additionally carry `failure_details` with resource type, frame URL,
same-origin status, redirect source, HTTP status or browser error, and occurrence
count. Query strings and credentials are removed from all reported URLs.

## Checks

Blocking errors:

- horizontal page overflow
- layout break when text is enlarged
- bottom controls penetrating the device safe area
- JavaScript page errors and `console.error`
- failed resources and HTTP errors
- a nearly blank page
- unreadable text below 10px
- broken visible images
- distorted canvas/image/video aspect ratio
- dead primary CTA
- a configured smoke-flow target or post-action assertion fails
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
  "viewport_preset": "full",
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

Use `"viewport_preset": "quick"` for the four-variant first gate, or replace it
with an explicit `"viewports"` list for a project-specific matrix. The preset
and explicit list are mutually exclusive.

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

### Bounded smoke flows

For a short client-side path, `smoke_flow` can describe an ordered sequence of
deterministic actions. It accepts at most eight steps from a closed set:

- `click`: click a selector;
- `fill`: fill a selector, with the value redacted from reports;
- `press`: press a key on a selector;
- `expect_visible`: require a selector to become visible;
- `expect_url`: require the current URL to match a regular expression;
- `expect_text`: require the visible element's rendered text, or a form
  control's current value, to match a case-insensitive regular expression.

```json
{
  "smoke_mode": "safe",
  "smoke_flow": [
    {"action": "fill", "selector": "#email", "value": "qa@example.com"},
    {"action": "click", "selector": "#continue"},
    {"action": "expect_visible", "selector": "#success"},
    {"action": "expect_url", "pattern": "#complete$"},
    {"action": "expect_text", "selector": "#status", "pattern": "^Ready$"}
  ]
}
```

The flow must contain a `click`, `fill`, or `press` action, followed later by at
least one `expect_visible`, `expect_url`, or `expect_text` assertion. A flow
cannot be combined with the single-CTA selector/assertion fields. The default
`safe` mode blocks HTTP after the initial page load, so flows are limited to
deterministic client-side behavior unless `smoke_mode` is explicitly changed to
`live`. Arbitrary JavaScript and user-defined detectors are not accepted.

`expect_text` reads `input`, `textarea`, and `select` values through
Playwright; all other elements use rendered text from the visible element.
Hidden descendants are not treated as delivered content. Reports retain the
pattern, source type, and observed length, but never copy the observed text into
evidence. This keeps text assertions deterministic without exposing values
typed into a page.

When a flow fails, `report.json` includes each completed step, the failed step,
and its error. The Agent summary names the exact action instead of reporting a
generic dead button.

Projects can keep several closed flows in one config and select one by name:

```json
{
  "smoke_flow_name": "checkout",
  "smoke_flows": {
    "login": [
      {"action": "fill", "selector": "#email", "value": "qa@example.com"},
      {"action": "click", "selector": "#continue"},
      {"action": "expect_visible", "selector": "#welcome"}
    ],
    "checkout": [
      {"action": "click", "selector": "#buy"},
      {"action": "expect_text", "selector": "#status", "pattern": "^paid$"}
    ]
  }
}
```

Flow names are closed identifiers matching `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`;
at most 16 definitions are accepted. Every definition is validated, but only
the selected flow runs. `smoke_flows` and the single inline `smoke_flow` are
mutually exclusive, as are named flows and the single-step `smoke_selector` /
success assertions, because every named flow must carry its own interaction and
assertion. Override the configured default with `--smoke-flow-name checkout`;
reports retain the selected name and redact fill values as before.

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

The eight public JSON payloads have packaged Draft 2020-12 schemas. Print one with
`ego-webqa --print-schema report`; see
[`docs/json-contracts.md`](docs/json-contracts.md) for names and the
compatibility policy.

Within one audit, up to three viewports render in isolated browsers
concurrently. This bounds slow-site wall time without sharing cookies, network
state, screenshots, or mutable evidence between viewports.

### MCP server

Expose the gate directly inside an AI coding agent:

```bash
python -m pip install ego-webqa
ego-webqa setup
ego-webqa mcp
```

`ego-webqa-mcp` remains available as a compatibility alias. An MCP client can
launch either command over stdio. The registry-compatible one-shot form is
`uvx ego-webqa@0.8.2 mcp`. The server advertises one tool, `audit_web_page`,
with structured success and blocking-error results:

```json
{
  "mcpServers": {
    "ego-webqa": {
      "command": "uvx",
      "args": ["ego-webqa@0.8.2", "mcp"]
    }
  }
}
```

Typical tool arguments are:

```json
{
  "url": "http://127.0.0.1:5173",
  "out_dir": ".qa/agent-a",
  "config": "/workspace/webqa-flow.json",
  "profile": "accessibility",
  "browser_engine": "webkit",
  "viewport_preset": "quick",
  "smoke_flow_name": "checkout",
  "smoke_scope": "all"
}
```

The `config` path is the MCP integration point for bounded `smoke_flow`
sequences, authenticated requests, ignore policies, and other settings that do
not need to be repeated in every tool call.

The MCP result is marked as an error when the report status is `fail`, while
the full report remains available as structured content. Authentication
environment variables are read by the server process, not passed as tool
arguments. This adapter deliberately remains a delivery-usability gate; it is
not a security scanner, WCAG certification tool, or visual-regression system.

### Governed value overrides

Projects can temporarily adjust a registered dimension without disabling the
dimension or adding arbitrary assertions. Every override requires an owner,
reason, and expiry; it may also change the effective `block`/`warn` severity
and use only that dimension's declared, safely overridable thresholds:

```json
{
  "overrides": [
    {
      "dimension_id": "tiny_fonts",
      "reason": "Typography migration tracked in DS-142",
      "owner": "design-system",
      "expires": "2026-11-30",
      "severity": "warn",
      "parameters": {
        "min_font_px": 13
      }
    }
  ]
}
```

The UTC audit date is the expiry clock. An override is active through its
`expires` date and automatically falls back to registry defaults the next day.
Unknown dimensions, unknown or unsafe parameters, duplicate dimension entries,
and conflicting values for a shared threshold are rejected.

`report.json` records the override in each affected issue and adds a
`governance` block containing active and expired declarations plus effective
parameters. `agent_summary.json` carries the same source metadata and reports
`overridden_dimensions`, `downgraded_blocks`, and `expired_overrides`. JUnit and
SARIF use the effective severity. An expired override remains visible for audit
but no longer changes detection or status. See
[`examples/webqa-governed.json`](examples/webqa-governed.json).

DeepSeek Harness can install the same MCP tool through the separate declarative
`dsh-ego-webqa` bundle. It reuses DSH's native MCP client instead of adding a
second QA implementation; see
[`docs/dsh-integration.md`](docs/dsh-integration.md) for the boundary and
acceptance criteria.

## GitHub Actions

This repository is also a composite GitHub Action. The Action installs the
package from the Action ref, installs the selected browser engine (Chromium by
default), runs the audit, uploads the report even when the audit fails, and
writes a concise privacy-safe root-cause table to the job summary:

```yaml
jobs:
  delivery-qa:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: ROY32172310/qa@v0.8.2
        with:
          url: ${{ vars.PREVIEW_URL }}
          browser-engine: webkit
          profile: accessibility
          viewport-preset: quick
          smoke-flow-name: checkout
          fail-on-warn: "true"
          smoke-scope: all
          baseline-report: .qa/known-good/report.json
          delta-gate: new
          http-username: ${{ secrets.PREVIEW_USERNAME }}
          http-password: ${{ secrets.PREVIEW_PASSWORD }}
          extra-http-headers: ${{ secrets.PREVIEW_HEADERS_JSON }}
          artifact-name: webqa-${{ github.run_id }}
```

For a local checkout of this repository, use `uses: ./` after checkout. The
Action's `safe` smoke mode is the default; set `smoke-mode: live` only when the
click is intentionally allowed to cause real side effects. See
[`examples/github-action.yml`](examples/github-action.yml) and
[`action.yml`](action.yml) for the full input set. The `@v0.8.2` tag is created
only after the same commit passes the full cross-platform CI matrix.

## Python API

```python
from ego_webqa import Settings, SmokeStep, audit

settings = Settings(
    smoke_flow=(
        SmokeStep("click", selector="#continue"),
        SmokeStep("expect_visible", selector="#success"),
    )
)
report = audit("https://example.com", settings=settings, output_dir="qa")
print(report.status)
```

## Scope and independence

This is a deterministic coarse gate for obvious delivery failures. A bounded
smoke flow can prove that one configured short client-side path reaches its
declared visible state, text/value, or URL; it does not prove business
correctness, that every supported browser matches, or that the page is secure.

Fixed report scope:

> 本报告仅覆盖多终端几何与基础体验的确定性粗检；业务主路径、跨浏览器兼容、安全合规需另行验证。

This repository is a standalone extraction of the general-purpose delivery
checks originally proven inside the ego project. It has no dependency on
`ego_protocol`, `ego_uri`, ego sharing, deployment, miniapp, or product-shell
semantics. Product-specific checks belong in plugins, not in the core.

## Benchmark and trust

The repository separates a controlled local regression benchmark from
real-world public-network observation:

- `benchmarks/` runs 128 independent synthetic cases across narrow, mobile,
  tablet, and desktop variants. It is the serial Chromium latency baseline and
  the correctness corpus for all 38 registered dimensions.
- `dogfood/` runs a fixed real-page sample and reports `url` and `local`
  outcomes separately. It is observational evidence, not a latency threshold,
  because network and target-site behavior change outside the tool's control.

Ground truth is declared per benchmark scenario; the evaluator does not import
detector thresholds to decide whether a result is correct.

```bash
python benchmarks/run.py
```

The evaluator reports exact dimension matches, case precision/recall/F1,
blocking false-positive and false-negative rates, dimension-level TP/FP/FN, and
complete audit latency. It writes machine-readable evidence plus a Markdown
summary. The 0.7.0 baseline is 128/128 exact with 0% blocking FP/FN, P50 357ms,
P95 1147ms, and max 3615ms in serial local Chromium:
[`docs/benchmark-2026-10-30-v0.7.0.md`](docs/benchmark-2026-10-30-v0.7.0.md).

These results measure curated synthetic fixtures in Chromium, not real-site
coverage or cross-engine parity. Firefox and WebKit have a separate real-browser
CI fixture for a clean page and a deterministic overflow failure. The
benchmark's value is regression pressure: its first run exposed a real
`accessibility` profile crash on standard `<label>` markup and duplicate CTA
root-cause reporting; both were fixed before the baseline was recorded.
See [`docs/performance-baselines.md`](docs/performance-baselines.md) for the
measurement contract and the two evidence classes.

## Development

```bash
uv sync --locked --all-extras
uv run --locked ego-webqa setup
uv run --locked python scripts/dev.py test
uv run --locked python scripts/dev.py coverage
uv run --locked python scripts/dev.py lint
uv run --locked python scripts/dev.py format-check
uv run --locked python scripts/dev.py typecheck
uv run --locked python scripts/dev.py benchmark
uv run --locked python scripts/dev.py package
uv run --locked python scripts/dev.py check   # lint + format + MyPy + coverage
uv run --locked python scripts/dev.py full    # check + Chromium benchmark
```

The same `scripts/dev.py` entry point and lockfile are used by GitHub Actions
on Linux, macOS, and Windows, preventing local and CI dependency or command
drift. Coverage enforces a 90% line/branch floor. See
[CONTRIBUTING.md](CONTRIBUTING.md) before adding a rule. Every rule needs a
positive control and an observed failure mode.

## License

MIT
