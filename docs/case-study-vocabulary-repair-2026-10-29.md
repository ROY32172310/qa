# Case study: an Agent repaired a generated page from deterministic evidence

This case study records one complete `ego-webqa` repair loop on a generated
vocabulary page. It is intentionally narrow: the goal is to show whether the
report gave an Agent enough evidence to make a safe repair and whether the same
deterministic gate accepted the result.

The source artifact was not modified. The audit ran against a copy, and the
before/after evidence is published on the
[live evidence board](https://roy32172310.github.io/qa/).

## Starting result

The default eight-viewport audit reported three root causes:

| Dimension | Severity | Evidence |
|---|---|---|
| `console_error` | block | A service-worker script returned HTTP 404 and emitted the same console error in all eight viewports. |
| `text_scale_layout_break` | block | At 1.5x text scaling on the two 360px viewports, the page became 5px wider than the viewport and visibly clipped footer content. |
| `transfer_budget` | warn | The initial document transferred 709KB in two requests, above the 400KB budget. |

The summary contained 10 blocking occurrences and eight warnings. The two
blocking families expanded across viewports, but `agent_summary.json`
aggregated them into one repair item per root cause.

Exact starting evidence:
[`before-agent-summary.json`](demo/data/before-agent-summary.json).

## Repair

The Agent changed only the two blocking causes:

1. Added the missing service-worker target, removing the 404 and its console
   error.
2. Allowed footer controls to wrap at enlarged text sizes, removing the 5px
   overflow.

It did not alter the large initial document. Suppressing the transfer warning
would have changed the evidence rather than the delivery problem.

## Verified result

Both the public CLI and MCP server were rerun against the repaired copy.

| Metric | Before | After |
|---|---:|---:|
| Root causes | 3 | 1 |
| Blocking occurrences | 10 | 0 |
| Warnings | 8 | 8 |
| Report status | fail | warn |
| MCP `is_error` | true | false |

The remaining warning is the genuine 710KB initial transfer. The CLI exited
`0` because the repaired page had no blocking defects, and the MCP result was
marked successful while retaining the warning.

Exact repaired evidence:
[`after-agent-summary.json`](demo/data/after-agent-summary.json).

## What this demonstrates

- A blocking item can be tied to a selector, affected viewport set, observed
  fact, and reproducible command without requiring private product context.
- Root-cause aggregation prevents eight repeated viewport entries from becoming
  eight separate repairs.
- The same result is consumable from the terminal and from an Agent through
  MCP.
- Warnings remain visible after blocking delivery defects are fixed; a green
  delivery decision does not erase an over-budget page.

This is one verified case, not a general precision or recall claim. The wider
real-page limitations remain documented in
[`real-world-dogfood-2026-10-29.md`](real-world-dogfood-2026-10-29.md).
