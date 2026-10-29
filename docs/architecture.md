# Architecture

`ego-webqa` is intentionally split into six core pieces:

1. `config.py`: public configuration and the only threshold source of truth.
2. `dimensions.py`: the closed, versioned registry of issue dimensions.
3. `probes.py`: browser-side facts, with no pass/fail decisions.
4. `engine.py`: Playwright orchestration and Python-side classification.
5. `reporting.py`: full reports, Agent summaries, JUnit, and SARIF adapters.
6. `cli.py`: argument handling, local serving, and exit codes.

The core package has one runtime dependency: Playwright. Browser binaries are
installed separately.

## Viewport variants

`Viewport` is the identity of one deterministic browser variant. Its public
specification is
`WIDTHxHEIGHT[:NAME][@TEXT_SCALE][~SAFE_BOTTOM_PX]`. The default matrix is the
cartesian product of 360/390px widths, 1.0x/1.5x text scaling, and 0/34px
simulated bottom safe areas. Explicit viewports replace that matrix.

Text scaling is applied through Playwright after initial rendering and before
layout facts are collected. A resulting width overflow is attributed to
`text_scale_layout_break`; an ordinary width overflow remains
`horizontal_overflow`. The 34px safe-area value is evidence for a deterministic
bottom-layer geometry check, not a claim that Chromium emulates a specific
physical device inset. Bottom fixed/sticky layers pass when they reserve enough
padding or explicitly consume `env(safe-area-inset-bottom)`.

The variant name, dimensions, text scale, and safe-area value are retained in
per-viewport evidence, screenshot names, and Agent reproduction commands.

## Browser engines

Each audit selects exactly one Playwright engine: `chromium`, `firefox`, or
`webkit`. Bundled Chromium is the default. Firefox and WebKit are opt-in and
require their own Playwright browser installation. The selected engine appears
in report runtime metadata, while `browser_channel` remains reserved for a
Chromium channel such as installed Chrome or Edge.

The same browser facts, issue model, thresholds, reports, smoke actions, and
concurrency boundary are used for every engine. This keeps the feature at the
orchestration layer instead of introducing engine-specific detector logic.
Firefox contexts omit Playwright's Chromium-specific `is_mobile` option while
retaining viewport dimensions, device scale, and touch capability.

Playwright WebKit is useful Safari-engine preview evidence, but it is not an
iOS device, macOS Safari, or a substitute for real-device certification.
Cross-engine comparison is deliberately not part of one audit: callers select
one engine per report and can compare stable report fields externally.

## Profiles

`baseline` covers delivery behavior across the configured viewport matrix.
`accessibility` adds deterministic document and interaction checks while
reusing the same browser facts, threshold model, issue model, and reporters.
Profile selection changes the issue rules, not the report schema.

## Bounded smoke flows

The optional `smoke_flow` is a closed sequence of at most eight deterministic
steps. Python owns orchestration and classification; Playwright performs only
five admitted operations: click, fill, press, visible-state assertion, and URL
assertion. Every flow must contain an interaction followed by a visible-state or
URL assertion.

The flow runs in the same isolated browser context as the viewport audit. In
the default safe mode, network requests are blocked after the initial load, and
`report.json` records every completed step plus the first failed step. Fill
values are redacted and never copied into evidence. The feature does not expose
arbitrary JavaScript, custom detectors, or a general-purpose E2E DSL.

## CI adapter

`action.yml` is a thin composite Action over the CLI. It owns runner setup,
selected-browser installation, and artifact upload; audit policy remains in
`Settings`. Action inputs are passed through environment variables and a Bash
argument array rather than interpolated into an executable script.

## Multi-agent boundary

Each `audit()` call or CLI process owns its Playwright lifecycles, browsers,
per-viewport contexts, local static server, and output directory. Settings are
frozen, mapping values are immutable, and reports are assembled per call. Agents
can therefore run in separate processes against the same target as long as each
selects a distinct output directory.

Within one call, up to three viewports run concurrently in independent threads,
each with its own Playwright runtime and browser. Results are reassembled in
configured viewport order; cookies, browser state, screenshots, and evidence
remain isolated.

The stable integration surface is:

- exit code: `0` pass/warn, `1` blocking issue, `2` invocation/runtime failure;
- `report.json` and `--json` output with explicit `schema_version`;
- `agent_summary.json` with root-cause aggregation and repair commands;
- per-viewport evidence for every aggregated root cause, plus structured network
  attribution (resource type, frame, redirect source, status, and error);
- relative screenshot references inside the report directory;
- JUnit and SARIF generated from the same issue list.

Sensitive headers, HTTP Basic credentials, and storage-state content are
accepted but never copied into the report. CI callers should provide secrets
through environment variables.

`mcp_server.py` is an optional protocol adapter over the same `audit()` and
reporting functions. It does not contain a second QA implementation. An MCP
tool call creates an isolated audit and returns the full versioned report as
structured content plus the compact Agent summary; blocking status is mapped to
the protocol's tool-error channel. The base package keeps its single Playwright
runtime dependency, while the `mcp` extra adds the protocol SDK for agent hosts.

`benchmarks/` is deliberately outside the installed package. Its suite declares
expected dimensions and clean controls; its runner invokes the public `audit()`
API against real local Chromium. The evaluator imports only the closed
dimension registry to validate IDs and default severity. It does not import
thresholds or detector branches, keeping the benchmark independent of the code
under test.

## Development quality gate

`scripts/dev.py` is the cross-platform source of truth for routine repository
checks. It runs from the current Python interpreter and sets the source path
explicitly, so direct pytest collection, child CLI processes, local development,
and CI resolve the same package.

- `test`: pytest without coverage overhead;
- `coverage`: pytest with JUnit output and line/branch coverage, failing below
  90%;
- `lint`: Ruff;
- `format-check`: Black check mode;
- `typecheck`: MyPy over the package, development script, and benchmark;
- `benchmark`: the complete public Chromium corpus;
- `package`: build and validate wheel/source distributions;
- `check`: lint, formatting, types, and covered tests;
- `full`: `check` followed by the complete benchmark.

GitHub Actions and the release workflow call these tasks instead of maintaining
duplicate command lists. A new mandatory quality gate belongs in this script
and is covered by the repository tests.

## Dimension registry

`dimensions.py` is the single source of truth for issue identity. Every emitted
issue must resolve to a registered dimension while reports are serialized.
Registry entries carry a stable id and version, detector ownership, default
severity, introducing release, profile, and parameter names. New checks enter
the registry as advisory warnings until real-site evidence supports blocking.

The registry is not user-extensible. Configuration can change exposed values,
but it cannot invent a dimension or arbitrary assertion.

## Scope and deliberate exclusions

The report covers multi-viewport geometry and deterministic baseline UX facts
in one selected rendering engine. A bounded smoke flow can verify one configured
short client-side delivery path, but business-path correctness, aggregate
cross-engine rendering parity, real-device Safari behavior, security,
observability, and accessibility certification require separate verification.

The core also does not know about:

- a deployment service or short-link provider;
- user/work/share identities;
- proprietary product shells;
- miniapp delivery conventions;
- a particular test runner or test-case database.

These can be implemented as external plugins or CI adapters without changing
the deterministic core.

## Compatibility

The JSON report uses `schema_version`. New optional fields may be added inside
the same major schema. Removing or changing existing field semantics requires a
new schema version.
