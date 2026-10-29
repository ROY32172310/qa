# Public benchmark baseline — ego-webqa 0.4.0

This baseline measures detector correctness and complete audit latency for
`ego-webqa 0.4.0` on controlled local fixtures. It is not a real-site survey.

## Environment

| Item | Value |
|---|---|
| Tool | `ego-webqa 0.4.0` |
| Browser | Bundled Chromium via Playwright `1.62.0` |
| Python | `3.11.16` |
| Platform | Linux x86_64, glibc `2.39` |
| Execution | Serial, `--jobs 1` |
| Suite SHA-256 | `36014b6df606defe8b016a6c23f2e2cb6dcb98cc9c2c06df5286e71d843c4639` |

## Result

| Metric | Result |
|---|---:|
| Expanded cases | 122 |
| Clean controls | 31 |
| Defect cases | 91 |
| Exact matches | 122 / 122 |
| Case precision | 100.00% |
| Case recall | 100.00% |
| Case F1 | 100.00% |
| Blocking false-positive rate | 0.00% |
| Blocking false-negative rate | 0.00% |
| Registered dimensions covered | 36 / 36 |
| Audit P50 | 341ms |
| Audit P95 | 1165ms |
| Audit max | 3610ms |

The four explicit slow cases account for most of the tail: slow first paint,
bounded network idle, delayed load event, and severe layout shift.

## Coverage

All 36 registered dimensions have an authored positive scenario. This baseline
adds explicit clean and defective fixtures for the two 0.4.0 dimensions:

- `text-scale-layout-break`: fixed, non-wrapping text pushes the document
  outside a 390px viewport at 1.5x text scale.
- `safe-area-penetration`: a fixed bottom action bar enters a simulated 34px
  device safe-area band.

Their clean controls retain wrapping/flexible actions and reserve safe-area
padding, respectively. The benchmark also continues to cover responsive
layout, media, network, timing, CTA, bounded-flow, and accessibility cases.

## Limits

- The fixtures are authored by the project and can share blind spots with the
  detector authors.
- Chromium is the only rendering engine exercised by this run.
- The safe area is a deterministic geometry simulation, not an emulation of a
  specific physical device.
- Browser text scaling is applied by the audit engine; it is not a native OS or
  assistive-technology text-size test.
- Mature public sites have authentication, ads, analytics, local-client probes,
  and variable payloads that synthetic fixtures do not represent.
- A perfect result means “no regression in this controlled corpus,” not
  “100% accurate on the web.”

Future real-site false positives and misses should be reduced to a minimal
fixture and added as a clean control or positive case before changing a rule.
