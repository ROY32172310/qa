# Public benchmark baseline — ego-webqa 0.5.0

This baseline measures detector correctness and complete audit latency for
`ego-webqa 0.5.0` on controlled local fixtures. Chromium remains the default
engine, so the 122-case benchmark remains directly comparable with the 0.4.0
baseline.

## Environment

| Item | Value |
|---|---|
| Tool | `ego-webqa 0.5.0` |
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
| Audit P50 | 340ms |
| Audit P95 | 1150ms |
| Audit max | 3602ms |

## Cross-engine verification

Firefox and WebKit are opt-in, so they have a separate real-browser regression
instead of multiplying every benchmark case by three engines. Both engines
passed the mobile clean-page and deterministic horizontal-overflow fixture:

| Engine | Clean page | Overflow detected | Runtime metadata |
|---|---|---|---|
| Firefox | PASS | PASS | `browser_engine=firefox`, `browser_channel=bundled-firefox` |
| WebKit | PASS | PASS | `browser_engine=webkit`, `browser_channel=bundled-webkit` |

The local smoke runs completed the demo mobile audit in 1.45 seconds with
Firefox and 0.97 seconds with WebKit. These timings are observations, not a
latency guarantee.

Playwright WebKit is Safari-engine approximation evidence. It is not a real
iPhone, iPad, or macOS Safari run.

## Limits

- The fixtures are authored by the project and can share blind spots with the
  detector authors.
- The full 122-case benchmark is Chromium-only. Firefox and WebKit have a
  focused clean/failure regression, not full dimension-parity coverage.
- The safe area is a deterministic geometry simulation, not an emulation of a
  specific physical device.
- Browser text scaling is applied by the audit engine; it is not a native OS or
  assistive-technology text-size test.
- A perfect result means “no regression in this controlled corpus,” not “100%
  accurate on the web.”
