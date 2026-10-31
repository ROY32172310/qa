# Real-world dogfood report: v0.8.2 on 2026-10-31

## Scope

This pass ran the published v0.8.2 detector set against the fixed 20-case
corpus in `dogfood/cases.json`:

- 14 public production or canonical Ego pages;
- six local generated-page artifacts;
- the default eight-variant mobile matrix for every case.

Raw evidence is intentionally ignored by Git:

- `dogfood-results/20261031-v0.8.2/result.json`;
- `dogfood-results/20261031-v0.8.2/summary.md`.

This run used the v0.8.2 `baseline` semantics, which still mixed deterministic
delivery findings with network-sensitive timing and transfer observations. The
report separates those classes below because mixing them changes the apparent
quality of otherwise clean production pages.

## Raw Result

All 20 cases completed with zero runtime errors. The raw run reported:

| Metric | Value |
|---|---:|
| Status | 10 fail / 9 warn / 1 pass |
| Raw issues | 131 |
| Completed-run P50 | 16,834 ms |
| Completed-run P95 | 23,579 ms |
| Public URL P50 / P95 | 19,136 / 23,881 ms |
| Local artifact P50 / P95 | 3,984 / 5,413 ms |

The public-network tail dominates the run. It is observational and is not a
claim about the tool's controlled local latency.

## Deterministic Delivery Findings

Excluding the performance family leaves 86 raw issue occurrences representing
20 repair items across ten pages:

| Dimension | Repair items | Raw occurrences | Triage |
|---|---:|---:|---|
| `text_scale_layout_break` | 6 | 14 | actionable blocking failures |
| `bottom_safe_area_penetration` | 4 | 16 | actionable blocking failures |
| `clipped_text` | 5 | 28 | actionable warnings |
| `small_tap_targets` | 4 | 20 | actionable warnings |
| `console_error` | 1 | 8 | missing service-worker script |

Ten pages have no deterministic finding after this split: all eight
`ego-user-*` pages plus the two public legal pages. The other ten pages retain
at least one blocking structural finding.

The dominant generated-page failures remain the shared Ego H5 footer:

- its action row overflows at 1.5x text scale;
- its action label is clipped;
- its bottom spacing does not reserve the 34px simulated safe area;
- several footer and game controls remain below the advisory 44px target.

The discovery page additionally overflows by 52px at 1.5x text scale. The
generated vocabulary artifact still loads a missing service worker.

## Network-Sensitive Observations

The raw v0.8.2 profile emitted 45 performance-family occurrences representing
20 observations:

| Dimension | Root observations | Raw occurrences |
|---|---:|---:|
| `slow_load_event` | 13 | 31 |
| `slow_first_paint` | 6 | 6 |
| `transfer_budget` | 1 | 8 |

Thirteen of the 14 public pages hit the bounded three-second load-event
deadline. This is consistent with the observed network tail, not with a stable
page defect:

- `app.html` completed in about 3.97 seconds;
- `privacy` completed in about 2.14 seconds;
- the word-quiz page observed about 2.43 seconds TTFB and 3.83 seconds total.

`slow_load_event` and `slow_first_paint` therefore do not belong in the
zero-config delivery verdict. The 709KB `transfer_budget` observation remains
useful, but it is also an explicitly requested performance concern rather than
a universal structural blocker in this default context.

## Product Decision

Change profile ownership rather than hiding or deleting evidence:

- `baseline`: deterministic geometry, runtime, resource, document, and
  interaction checks;
- `performance`: baseline plus first paint, load-event deadline, network-idle,
  and transfer/request budgets;
- `accessibility`: baseline plus deterministic accessibility checks;
- `full`: baseline plus performance and accessibility.

The JSON report continues to retain raw timing measurements in every profile.
The selected profile controls which registered dimensions may produce findings,
and the dimension registry remains the single source of truth.

This change must be validated as a later release candidate. It is not being
published as `0.8.3` solely to run the release pipeline.

## Next Evidence

The next real-world batch should:

1. rerun the same corpus under the new `baseline` and `performance` profiles
   and confirm the deterministic findings are unchanged;
2. record controlled-network performance observations separately;
3. recruit 5-10 external AI-generated pages before deciding whether the profile
   split and any new detector deserve a release.
