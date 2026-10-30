# Report and integration contract

Read this reference when configuring a bounded interaction, interpreting
`agent_summary.json`, or explaining the result to an end user.

## Invocation

Prefer the MCP tool named `audit_web_page` when it is already installed. Pass
the page URL and an output directory; use a JSON config only for settings that
the MCP result does not expose directly.

Minimum CLI call:

```bash
ego-webqa "https://example.com" --out .qa/agent-delivery --json
```

For a quick repair loop, `--preset quick` runs four pairwise mobile variants.
The default `full` matrix has eight variants and should back the final delivery
claim. `doctor --json` reports runtime readiness; a doctor failure is an
environment problem, not evidence that the target page is broken.

Exit codes are part of the contract:

- `0`: no blocking finding; warnings may remain.
- `1`: at least one blocking finding was observed.
- `2`: the audit could not run reliably; do not call the page healthy or broken.

## Findings

`agent_summary.json` is the preferred result for an agent to consume. For each
root cause it provides:

- `dimension_id` and effective `severity`;
- the affected selector and a short text excerpt;
- the viewport, text-scale, safe-area, or flow trigger;
- a repair direction and a reproduction command;
- evidence grouped by viewport.

Fix blocking items in impact order, rerun the same command, and stop only when
the exit code is `0`. Warnings such as `clipped_text` require judgment: repair
user-relevant truncation, but do not break an intentional visual treatment just
to eliminate the warning.

## Baseline gate

Pass an earlier `report.json` to distinguish new delivery debt from an already
known root cause:

```bash
ego-webqa "https://example.com" \
  --baseline-report .qa/baseline/report.json \
  --gate new \
  --out .qa/current
```

`delta.json` classifies roots as `new`, `persistent`, `changed`, or `resolved`.
The `new` gate fails only for new or expanding blocking roots. Target,
configuration, and runtime compatibility must match unless the user explicitly
allows a comparison across them.

## Bounded smoke flow

Use a configured flow when the delivery claim includes one short client-side
interaction. Every flow must end in a visible-text, visible-element, or URL
assertion.

```json
{
  "smoke_flow": [
    { "action": "click", "selector": "#continue" },
    { "action": "expect_visible", "selector": "#success" }
  ]
}
```

The closed action set is `click`, `fill`, `press`, `expect_visible`,
`expect_text`, and `expect_url`, with at most eight steps. This is not a general
E2E language. Keep safe smoke mode unless the user explicitly accepts a real
submission, purchase, or destructive side effect.

To retain several reviewed flows, place a closed `smoke_flows` object in the
JSON config and select one with `--smoke-flow-name NAME`. Unselected flow
contents are not copied into the report. Do not add arbitrary JavaScript or
user-defined detector code.

## Stable contracts and feedback

The public `1.0` contracts are `report`, `agent-summary`, `dimensions`,
`feedback-bundle`, `delta`, `doctor`, `browser-install`, and `setup`. Validate a received payload against
the bundled schema instead of assuming package compatibility:

```bash
ego-webqa --print-schema agent-summary
```

`feedback_bundle.json` is privacy-first and omits target URLs or paths,
selectors, page text, messages, raw evidence, screenshots, storage state, and
configuration contents. Use `ego-webqa feedback --report PATH` to rebuild it
from an existing report. Contextual fields require explicit include flags and
the user's approval.

## Boundary

A pass proves that the configured deterministic checks did not find an obvious
delivery failure. It does not prove business correctness, security, WCAG
compliance, visual regression, every browser's parity, or the complete user
journey. Always report those limits with the result.
