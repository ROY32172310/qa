# Changelog

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
