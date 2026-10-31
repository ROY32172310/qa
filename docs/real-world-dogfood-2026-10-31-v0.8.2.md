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

## Profile-Split Validation

The unreleased candidate was rerun against the same manifest and public CLI
with an explicit profile override. This changes only which registered dimension
families are emitted; the raw browser measurements remain in `report.json`.

### Baseline

- Evidence: `dogfood-results/20261031-profile-baseline/result.json`.
- 20/20 audits completed with zero runtime errors.
- Status: 10 fail / 10 pass.
- Raw occurrences: 86.
- P50/P95: 14,683/21,593 ms.
- Public URL P50/P95: 15,235/23,347 ms.
- Local artifact P50/P95: 2,768/2,818 ms.
- Performance-family findings: zero.

The baseline occurrences match the v0.8.2 split exactly:
`text_scale_layout_break` 14, `clipped_text` 28,
`bottom_safe_area_penetration` 16, `small_tap_targets` 20, and
`console_error` 8. These 86 occurrences still represent the same 20 repair
items across ten pages.

### Performance

- Evidence: `dogfood-results/20261031-profile-performance/result.json`.
- 20/20 audits completed with zero runtime errors.
- Raw occurrences: 130.
- P50/P95: 15,436/22,847 ms.
- Structural findings: the same 86 baseline occurrences.
- Performance additions: 13 `slow_load_event` roots (29 occurrences), three
  `slow_first_paint` roots (four occurrences), and one `transfer_budget`
  observation (eight occurrences).

One public page, `ego-user-workbench`, received HTTP 503 on two viewports in
the performance batch, producing `http_error` and `blank_page` evidence. That
page passed the full baseline batch. A dedicated baseline repeat then passed
with zero findings, while a dedicated performance repeat reached the page
successfully and reported only one `slow_load_event` warning. The 503 is
therefore an upstream transient, not a profile-dependent structural result:

- `dogfood-results/20261031-profile-baseline-workbench-repeat/result.json`;
- `dogfood-results/20261031-profile-performance-workbench-repeat/result.json`.

The split is functionally validated. It remains unreleased until external
AI-generated pages provide independent evidence.

## Manual Triage

The baseline's 20 root causes were reviewed against selectors, geometry,
trigger viewports, and representative screenshots. All 20 are visible true
positives; no structural false positive was found. Eighteen belong to the
shared generated-page footer and control system. Details and the false-negative
boundary are recorded in
`docs/real-world-triage-2026-10-31-baseline.md`.

## Next Evidence

The next real-world pass should recruit 5-10 external AI-generated pages,
capture the exact page-generation context, and record one classified finding
per participating user where possible. Controlled-network performance runs
should remain separate from the default delivery verdict.
