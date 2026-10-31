# Baseline dogfood triage: 2026-10-31

## Scope

This review classifies the 20 deterministic root causes produced by the fixed
20-page corpus under the unreleased `baseline` profile. Evidence:
`dogfood-results/20261031-profile-baseline/result.json`.

The review compared the reported selector, text, geometry, trigger viewports,
and screenshots. Representative mobile screenshots were inspected at 360px and
390px, including 1.5x text scale and a simulated 34px bottom safe area. Clean
pages were also inspected for visible structural misses. This is a manual
first-party review, not independent user validation.

## Classification

| Page | Dimension | Verdict | Visible evidence |
|---|---|---|---|
| `egohub-discover` | `text_scale_layout_break` | TP | The `white-space: nowrap` English tagline is clipped at 1.5x text scale. |
| `egohub-discover` | `small_tap_targets` | TP | Featured cards are 148x39px and the compact install control is 40x44px. |
| `egohub-work-tetris` | `text_scale_layout_break` | TP | The shared footer action extends beyond the 360px viewport. |
| `egohub-work-tetris` | `clipped_text` | TP | Footer labels are visibly cut at the viewport edge. |
| `egohub-work-word-quiz` | `text_scale_layout_break` | TP | The same footer action overflows under 1.5x text. |
| `egohub-work-word-quiz` | `clipped_text` | TP | Footer labels are partially clipped. |
| `egohub-work-vocabulary` | `text_scale_layout_break` | TP | The shared footer action overflows under 1.5x text. |
| `egohub-work-vocabulary` | `clipped_text` | TP | Footer labels are partially clipped. |
| `ego-generated-accounting` | `text_scale_layout_break` | TP | The footer action is pushed beyond the viewport. |
| `ego-generated-accounting` | `clipped_text` | TP | Footer metadata and action text are clipped. |
| `ego-generated-vocabulary` | `console_error` | TP | The page emits a service-worker script fetch 404 on all eight variants. |
| `ego-generated-vocabulary` | `text_scale_layout_break` | TP | The footer action overflows under 1.5x text. |
| `ego-generated-vocabulary` | `clipped_text` | TP | Footer action text is hidden by the viewport boundary. |
| `ego-generated-click-counter` | `bottom_safe_area_penetration` | TP | The fixed footer occupies the simulated 34px device safe area. |
| `ego-generated-noodle-shop` | `bottom_safe_area_penetration` | TP | The fixed footer occupies the simulated safe area and obscures page content. |
| `ego-generated-noodle-shop` | `small_tap_targets` | TP | Menu actions remain below the 44px target threshold. |
| `ego-public-math-practice` | `bottom_safe_area_penetration` | TP | The fixed attribution/action bar covers content inside the safe-area band. |
| `ego-public-math-practice` | `small_tap_targets` | TP | Answer controls remain below the 44px target threshold. |
| `ego-generated-games-gallery` | `bottom_safe_area_penetration` | TP | The fixed footer occupies the simulated safe area. |
| `ego-generated-games-gallery` | `small_tap_targets` | TP | Seven filter controls remain below the 44px target threshold. |

Result: 20 true positives, zero structural false positives.

## False-Negative Review

The other ten pages had no stable structural finding in the representative
screenshots. `ego-user-gallery` showed a loading state at 360px while a 390px
variant reached the rendered gallery. The `performance` profile reports this
page as `slow_load_event`; moving that timing signal out of `baseline` therefore
did not discard the observation. It is a performance/readiness signal, not a
separate structural false negative.

The screenshots establish no obvious deterministic miss on the clean set, but
they do not prove exhaustive interaction or cross-browser correctness. Those
remain outside this review and outside the `baseline` contract.

## Product Consequence

Eighteen of the 20 root causes belong to the shared generated-page footer and
control system: footer overflow/clipping, safe-area penetration, and sub-44px
targets. The remaining two belong to the public discovery page's tagline and
compact controls.

No detector loosening is justified by this sample. The next action is to feed
the shared-footer evidence back to the Ego generator and rerun the same
deterministic baseline after repair. External AI-generated pages are still
needed before claiming market-wide false-positive accuracy.

The actionable upstream contract is
`docs/generated-footer-repair-brief-2026-10-31.md`.

The repaired generator was subsequently assembled and audited against three
fresh pages. All three passed the default eight-viewport baseline with zero
errors and warnings, including regenerated copies of the accounting and
vocabulary projects. Details and the production-rollout boundary are recorded
in `docs/upstream-footer-repair-2026-10-31.md`.
