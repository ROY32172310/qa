# Real-world dogfood report: 2026-10-29

This report evaluates `ego-webqa 0.4.0` against the fixed 20-page corpus in
`dogfood/cases.json`. It separates page defects from execution failures and
records whether an Agent can act on each finding without importing private
product context.

## Method

- Environment: Linux, Python 3.11.16, system Chrome, bundled default eight
  viewports (`360/390px` x `1.0/1.5x` text scale x `0/34px` safe area).
- The runner invokes the public CLI and records status, wall time, report,
  Agent summary, command, and screenshot artifacts.
- CTA and bounded flow smoke were disabled in this pass. This sample measures
  rendering, layout, network, and timing evidence only.
- Ground truth was established from screenshots and evidence fields. A stable
  finding was labeled `TP` only when the rendered page visibly affected content
  or interaction. Unstable timing observations and incomplete runs were not
  counted as page defects.

The primary evidence set is
`dogfood-results/2026-10-29-v040-final3/result.json`.

## Execution result

| Metric | Result |
|---|---:|
| Cases | 20 |
| Completed audits | 19 |
| Runtime-incomplete cases | 1 |
| Pass / warn / fail | 4 / 6 / 9 |
| P50 / P95 / max completed runtime | 14.25s / 24.71s / 24.71s |

The completed local generated pages took roughly 2.4-2.6 seconds to audit.
Production pages took 11-25 seconds in this network and browser environment.
They are useful throughput evidence but do not support a 10-second promise for
uncontrolled public network pages.

`ego-user-gallery` did not complete within the 180-second case deadline. A
separate run completed in 22.0 seconds. After the runner was hardened with a
process-group deadline, two consecutive isolated runs completed in 22.1 and
20.8 seconds. The gallery can still intermittently stall after screenshots are
written, so it is classified as an execution reliability defect, not a page
`FP`.

## Stable findings

| Finding family | Cases | Classification | Evidence |
|---|---|---:|---|
| Text-scale layout break | 5 | TP, block | 30px overflow in Discover; 5-7px overflow in four generated works at 1.5x. Screenshots show cropped footer/action content. |
| Bottom safe-area penetration | 4 | TP, block | Fixed footer gaps of 0px or 10px against a simulated 34px device band. |
| Small tap targets | 3 | TP, warning | Math practice: 34 controls at 37px high; noodle shop and games gallery: 7 controls at 40px high. |
| Service-worker 404 | 1 | TP, block | The generated vocabulary page's service-worker script returns 404 and emits `console.error` in every viewport. |
| Transfer budget | 1 | TP, warning | Generated vocabulary transfers 709KB for the initial document, above the 400KB budget. |

No stable blocking finding was identified as a false positive.

The 5px text-scale findings remain blocking. Although the raw overflow is
small, the enlarged-text screenshots show that footer/action content is
clipped rather than simply shifting into harmless scroll space. A threshold
based on pixel size would hide a real interaction failure.

### Timing warnings

The run produced advisory `slow_first_paint` and `slow_load_event` findings on
production pages. These varied across viewports and runs and were not treated
as stable page defects. They remain useful observations, but require repeated
clean-network measurements before a creator is asked to change the page.

## False-negative limits

This pass does not establish a complete false-negative rate:

- CTA and flow smoke were disabled, so dead interactions and broken short paths
  were not exercised.
- Screenshots were reviewed manually for obvious breakage; there is no visual
  baseline or full cross-browser comparison.
- Slow timing and production network failures need repeated samples before they
  can be separated from environment noise.

A second pass should enable a small, explicitly bounded set of smoke flows and
sample unstable warnings more than once.

## Repair loop

The original generated vocabulary page was copied to
`dogfood-results/repair-vocabulary/src/`; the source artifact was not modified.
The repair:

- added the missing service worker, removing the 404 and console error;
- allowed footer controls to wrap under injected text scaling, removing the
  5px overflow;
- left the large initial document unchanged.

CLI and MCP re-audits both returned zero blocking errors. The only remaining
root cause was the genuine 710KB transfer-budget warning, and the MCP result
reported `is_error: false`. This verifies the generate -> audit -> repair ->
re-audit loop with both public integration surfaces.

The first evidence run exposed one repair-quality issue: the safe-area hint
said to reserve 16px while the detector required 34px. The hint now derives its
value from the effective threshold:
`max(34px, env(safe-area-inset-bottom))`.

## Reliability changes from this pass

- Navigate with `wait_until="commit"` and bound DOM readiness separately.
- Retry one transient navigation timeout in a fresh browser context.
- Downgrade an isolated navigation timeout to a warning when other viewports
  loaded; an all-viewport failure remains blocking.
- Measure layout shift only at `1.0x` text scale to avoid tool-induced reflow.
- Run every dogfood case in a separate process group and terminate the complete
  process tree at its deadline.
- Add opt-in stage tracing with `EGO_WEBQA_TRACE=1` for future unbounded-wait
  diagnosis.

A 60-second gallery deadline was verified end to end: the command returned at
60.004 seconds and left no Chrome process behind.

## Decision

The deterministic rule set is directionally sound on real pages and has a
verified repair loop. The next release should remain a patch-level reliability
release unless bounded-flow evidence adds a new user-facing capability.

Before the next release, resolve or further isolate the gallery stall, run the
full quality gate, and keep execution-incomplete cases out of detector
precision/recall statistics.
