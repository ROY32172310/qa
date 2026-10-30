# Real-world dogfood report: v0.8.0 on 2026-10-30

## Scope

This pass ran the published v0.8.0 detector set against the fixed 20-case
corpus in `dogfood/cases.json`:

- 14 public production or canonical Ego pages;
- six local generated-page artifacts, four with bounded smoke flows;
- the default eight-variant mobile matrix for every case.

The run was repeated after the first v0.8.0 pass to characterize the one
timing-sensitive warning described below. The raw evidence is intentionally
ignored by Git:

- primary run: `dogfood-results/20261030-v0.8.0/result.json`;
- repeat run: `dogfood-results/20261030-v0.8.1-overflow-locators/result.json`;
- targeted owner checks:
  `dogfood-results/20261030-discover-owner-check/result.json` and
  `dogfood-results/20261030-vocabulary-owner-check-2/result.json`.

## Result

Both full runs completed all 20 cases with zero runtime errors. The repeat run
had a completed-run P50 of 8.1 seconds and P95 of 17.7 seconds. Public pages
account for nearly all of that tail; the six local generated artifacts
completed with a P95 of 2.8 seconds.

The primary run found 95 raw findings. After aggregation by page, dimension,
and root cause, those represented 22 repair items:

| Dimension | Root causes | Severity | Triage |
|---|---:|---|---|
| `text_scale_layout_break` | 6 | block | actionable true positives |
| `bottom_safe_area_penetration` | 4 | block | actionable true positives |
| `console_error` | 1 | block | actionable service-worker 404 |
| `clipped_text` | 5 | warn | actionable shared-footer clipping |
| `small_tap_targets` | 4 | warn | actionable target-size failures |
| `transfer_budget` | 1 | warn | actionable 709KB initial transfer |
| `slow_first_paint` | 1 | warn | non-stable timing observation |

Ten pages passed with no findings. That includes all eight public
`ego-user-*` application pages, the two public legal/static pages, and the
repaired controls represented by the synthetic benchmark. No inspected result
needed to be reclassified as a valid false positive in this sample.

This is a small first-party corpus, not a market-wide precision claim. The
useful conclusion is narrower: on these production and canonical generated
pages, the blocking rules found visible failures while the mature user-facing
pages remained clean.

## What the failures shared

The dominant generated-page failures came from the shared Ego H5 footer rather
than unrelated application logic:

- at 1.5x text scale, its nowrap action row exceeded the layout viewport by
  4-12px;
- its brand/action label was clipped because the container hid overflow;
- its bottom padding did not reserve the simulated 34px safe area;
- several footer and game controls remained below the 44px advisory target.

The discovery page exposed a separate 52px text-scale overflow in its English
tagline. One generated vocabulary artifact also loaded a missing service
worker, producing a console error, and transferred 709KB in its initial HTML.

These are actionable delivery defects. They are also repeated skeleton-level
issues, which explains why issue counts are high even though the number of
distinct repair causes is much smaller.

## Timing observation

The first run reported a 4.8-second first-contentful-paint warning on one
generated learning page. The repeat run did not reproduce it, while every
structural finding remained stable. Do not treat that individual timing
finding as a confirmed regression without repeated samples. Layout, clipping,
safe-area, and tap-target findings are structural and remained reproducible.

## Workflow change from this evidence

The report initially identified every text-scale overflow at `html`. That was
technically true but did not tell an Agent what to change. The probe now
reports up to five unclipped overflowing elements with selectors, labels,
boxes, and measured pixel overflow.

Real-page checks confirmed:

- the vocabulary page now points at
  `body > div:nth-of-type(2) > div:nth-of-type(2) > a` with the visible label
  `我也要创建 →` and a measured 9px overflow;
- the discovery page points at
  `body > div:nth-of-type(3) > div:nth-of-type(1)` with the English tagline and
  a measured 52px overflow;
- a button positioned far inside a horizontally scrollable carousel is
  excluded because it does not own document-level overflow.

The detection dimension, severity, and thresholds did not change. This is a
repair-addressability improvement, not a new broad rule.

## Decision

Keep the current deterministic rule boundary. The next detector work should
still require a new reproducible failure mode. Near-term product work should
focus on first-trial conversion and real external feedback rather than adding
more checks from this first-party corpus.
