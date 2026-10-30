# Changelog

## Unreleased

- Add `ego-webqa doctor` to verify Python, MCP, Playwright, browser binaries,
  system browser channels, and a real headless launch before running an audit.
- Generate a default `feedback_bundle.json` whose allowlist omits target URLs,
  local paths, custom viewport names, selectors, page text, messages, raw
  evidence, screenshots, and configuration contents. Explicit CLI flags can
  add contextual fields for private issue reports.
- Render a concise root-cause table in the GitHub Action job summary from the
  privacy-safe feedback bundle instead of copying the full Agent report.
- Add baseline/delta report comparison with stable dimension-plus-root
  fingerprints, strict target/configuration/browser compatibility, and
  `new`, `persistent`, `changed`, and `resolved` classification.
- Add `--baseline-report ... --gate new` to the audit CLI and composite Action.
  Unchanged blocking debt remains visible without failing every rerun; new or
  expanding blocking roots fail the gate.

## 0.7.0 - 2026-10-30

- Add the advisory `clipped_text` geometry check for visible text hidden by an
  overflow boundary. Explicit ellipsis, line-clamp, and scroll affordances are
  treated as intentional controls, and the clip tolerance is governed through
  `text_clip_tolerance_px`. A three-page production dogfood sample found the
  expected footer-label truncation without reporting the two clean layouts.
- Add the closed `expect_text` smoke-flow assertion for visible rendered text
  and current input, textarea, or select values. Matching is case-insensitive,
  mismatches use the dedicated blocking
  `smoke_flow_text_assertion_failed` dimension, and observed page text is not
  copied into reports.
- Retry document measurement across a bounded navigation replacement and
  request one fresh-context retry when text scaling or measurement loses the
  document root, avoiding internal `TypeError` findings and false blank-page
  results on slow public pages.
- Extend the real-page dogfood manifest with case-level bounded `smoke_flow`
  support and verify three short generated-page interactions through the public
  CLI configuration path.

## 0.6.0 - 2026-10-29

- Add project-level governed value overrides with mandatory `reason`, `owner`,
  and `expires` fields, safe numeric threshold mappings, and severity changes
  for registered dimensions.
- Apply overrides from the same JSON config through the Python API, CLI, MCP,
  and GitHub Action. Unknown dimensions or parameters, duplicate declarations,
  and conflicting values for shared thresholds are rejected.
- Record active, expired, and effective override state in reports and Agent
  summaries; use effective severity in JUnit/SARIF and automatically restore
  defaults after the UTC expiry date.

## 0.5.0 - 2026-10-29

- Add opt-in Playwright Firefox and WebKit engines through
  `--browser-engine`, the Python `Settings` API, MCP `audit_web_page`, and the
  GitHub Action.
- Keep bundled Chromium as the default engine and run exactly one rendering
  engine per audit, so existing cost and latency behavior remains unchanged.
- Add real Firefox and WebKit CI fixtures covering both a clean mobile page and
  a deterministic horizontal-overflow failure.
- Record the selected engine separately from the browser channel in report
  runtime metadata and generated Agent reproduction commands.
- Document that Playwright WebKit is a Safari-engine approximation, not a
  real-device Safari compatibility claim.

## 0.4.2 - 2026-10-29

- Publish `ego-webqa` as a first-class MCP Registry package with a canonical
  `uvx ego-webqa@0.4.2 mcp` stdio entry point; keep `ego-webqa-mcp` as a
  compatibility alias.
- Make the MCP adapter part of the base install, add the official PyPI
  ownership marker and `server.json`, and validate their version, transport,
  repository, and package identity in CI.
- Publish Registry metadata automatically after successful PyPI releases using
  verified `mcp-publisher` binaries and GitHub Actions OIDC.
- Add a DSH integration decision: keep the Python audit core authoritative and
  package DSH's native MCP client as a separate declarative bundle, avoiding a
  second tool or detector implementation.

- Add a public evidence board built from a real before-and-after dogfood run,
  with all eight mobile matrix screenshots, aggregated root causes, and
  machine-readable Agent summaries.
- Deploy the static evidence board to GitHub Pages without exposing a hosted URL
  audit service or introducing a server-side request surface.

## 0.4.1 - 2026-10-29

- Add PyPI project links and put the first successful audit, sample Agent
  finding, and real-page dogfood evidence at the top of the README.
- Add a fixed 20-page real-world dogfood corpus, runner, result schema, and
  review protocol with a 180-second default per-case deadline.
- Navigate on document commit, bound DOM/load readiness separately, retry one
  transient navigation timeout in a fresh browser context, and downgrade an
  isolated timeout when other viewports rendered successfully.
- Measure layout shift only at normal text scale so the injected enlargement
  does not manufacture CLS findings.
- Terminate the complete audit process group at the dogfood deadline instead of
  waiting indefinitely on inherited browser processes, with a Windows-safe
  process-tree path and type boundary.
- Add opt-in `EGO_WEBQA_TRACE=1` stage tracing for diagnosing unbounded browser
  waits.
- Make safe-area repair guidance use the effective detector threshold rather
  than a stale 16px value.

## 0.4.0 - 2026-10-29

- Replace the default device mix with a faster narrow-mobile matrix covering
  360px and 390px widths, 1.0x and 1.5x text scaling, and 0px or 34px simulated
  bottom safe areas.
- Add blocking `text_scale_layout_break` and
  `bottom_safe_area_penetration` dimensions with clean controls and positive
  fixtures in the public benchmark.
- Expand the public benchmark to 122 cases and 36 registered dimensions, with
  a 122/122 exact-match regression baseline.
- Preserve text scale and safe-area values in viewport evidence and generated
  reproduction commands.
- Add a cross-platform `scripts/dev.py` quality gate for tests, branch
  coverage, Ruff, Black, MyPy, benchmarks, and package validation.
- Run the same development entry point in GitHub Actions and release packaging
  so local and remote checks do not drift.

## 0.3.1 - 2026-10-29

- Add a public 118-case synthetic benchmark with clean controls and positive
  fixtures covering all 34 registered dimensions, bounded flows, and the
  accessibility profile.
- Add benchmark precision, recall, blocking false-positive/false-negative, and
  per-dimension latency reporting without importing detector thresholds into
  the evaluator.
- Run the benchmark on Linux CI and publish its machine-readable evidence as a
  workflow artifact.
- Fix the accessibility profile crashing on standard explicit `<label for>`
  markup.
- Report a CTA click exception as `cta_page_error` without also emitting the
  less specific `dead_primary_cta` finding.

## 0.3.0 - 2026-10-29

- Add an opt-in bounded smoke flow for short client-side delivery paths.
  Supported steps are `click`, `fill`, `press`, `expect_visible`, and
  `expect_url`; arbitrary JavaScript and user-defined detectors remain
  unsupported.
- Require an interaction followed by a visible-state or URL assertion and cap
  flows at eight steps so a pass always has deterministic post-action evidence.
- Keep the default `safe` mode: post-load network requests are blocked while
  the flow runs. Flow input values are redacted from reports and Agent
  summaries.
- Add blocking dimensions for missing flow targets, failed expectations, and
  page-level exceptions raised during a flow.

## 0.2.3 - 2026-10-28

- Add structured request-failure attribution to network evidence: resource
  type, frame URL, same-origin status, redirect source, status/error, and
  occurrence count, with credentials and query strings removed.
- Preserve evidence from every affected viewport in an aggregated Agent repair
  item through `evidence_by_viewport`.
- Measure fixed-overlay coverage from viewport intersection so fully offscreen
  slide-out panels are no longer reported as huge overlays.
- Ignore aspect-ratio drift below a configurable 48px rendered-media floor;
  small icons affected by CSS pixel rounding no longer block delivery.

## 0.2.2 - 2026-10-28

- Add a closed, versioned dimension registry and expose it through
  `ego-webqa --list-dimensions`.
- Emit `agent_summary.json` with root-cause aggregation, selectors, affected
  viewport combinations, repair hints, and reproducible commands.
- Include the same agent summary in MCP structured and text results.
- Keep a rendered page auditable when its `load` event exceeds the bounded
  deadline; report the delayed load as an advisory warning instead of replacing
  all page evidence with a navigation failure.
- Deduplicate browser transport errors, ignore intentional request aborts and
  custom-app launch attempts, and redact credentials/query data from network
  evidence.
- Run up to three isolated viewport browsers concurrently while preserving the
  configured viewport order and per-call evidence isolation.
- State the deterministic coarse-check boundary in reports and documentation.

## 0.2.1 - 2026-10-28

- Add authenticated preview support through storage state, HTTP Basic credentials,
  and additional request headers without exposing secrets in command lines.
- Run CTA smoke checks across every viewport when requested and support an
  explicit assertion-required contract.
- Exclude ignored requests from both request and transfer budgets.
- Record readiness evidence for ready selectors, fonts, and network idle.
- Ignore the browser's automatic failed favicon request instead of reporting it as
  a page console error.
- Add composed-tree Shadow DOM discovery and actionable selectors to DOM and
  accessibility evidence.
- Make screenshot references portable and relative to the report directory.
- Add multi-agent-safe machine invocation documentation and deterministic
  JUnit diagnostics for cross-platform CI.
- Add an optional MCP stdio server with a structured `audit_web_page` tool for
  agent-native blocking and repair loops.
- Fix the Windows Chromium installation path and update GitHub Actions runtimes.

## 0.2.0 - 2026-10-28

- Fix the public SARIF tool URI.
- Declare the formatter and packaging tools used by CI.
- Verify coverage, wheel installation, and package metadata in CI.
- Document source and PyPI installation paths.
- Add tag-triggered PyPI Trusted Publishing.
- Use real mobile browser contexts with touch, mobile user agents, and evidence.
- Make primary-CTA smoke safe by blocking post-load network requests.
- Validate configuration field types and threshold ranges.
- Wait for an optional ready selector or bounded network-idle period.
- Ignore known console and failed-request noise with regex policies.
- Short-circuit secondary findings after a failed main document.
- URL-encode local filenames used by the bundled static server.
- Require explicit selector and URL assertions for CTA success when configured.
- Add an `accessibility` profile for deterministic document, control, image,
  heading, ID, focus-order, and ARIA-hidden checks.
- Add a composite GitHub Action with safe smoke defaults, profile selection,
  browser setup, and always-on report artifact upload.

## 0.1.0 - 2026-10-27

- Initial standalone extraction.
- Multi-viewport Chromium audit.
- Layout, readability, media, network, timing, and primary-CTA checks.
- JSON, JUnit XML, SARIF, and screenshot artifacts.
- Independent JSON configuration and no ego-private dependencies.
