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

## Boundary

A pass proves that the configured deterministic checks did not find an obvious
delivery failure. It does not prove business correctness, security, WCAG
compliance, visual regression, every browser's parity, or the complete user
journey. Always report those limits with the result.
