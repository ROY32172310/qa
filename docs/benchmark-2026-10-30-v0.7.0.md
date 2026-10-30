# Public benchmark baseline — ego-webqa 0.7.0

The 0.7.0 baseline extends the public deterministic corpus with positive and
clean controls for the advisory `clipped_text` dimension. It also covers the
bounded `expect_text` smoke assertion, navigation-replacement retries, and the
real-page dogfood path exercised by the release candidate.

## Environment

| Item | Value |
|---|---|
| Tool | `ego-webqa 0.7.0` |
| Browser | Bundled Chromium via Playwright `1.62.0` |
| Python | `3.11.16` |
| Platform | Linux x86_64, glibc `2.39` |
| Execution | Serial, `--jobs 1` |
| Suite SHA-256 | `867fee7d62385b32d3ea82087274c65e8cf420e0740342e2bccee59ec6f593f8` |

## Result

| Metric | Result |
|---|---:|
| Expanded cases | 128 |
| Clean controls | 33 |
| Defect cases | 95 |
| Exact matches | 128 / 128 |
| Case precision | 100.00% |
| Case recall | 100.00% |
| Case F1 | 100.00% |
| Blocking false-positive rate | 0.00% |
| Blocking false-negative rate | 0.00% |
| Registered dimensions covered | 38 / 38 |
| Audit P50 | 357ms |
| Audit P95 | 1147ms |
| Audit max | 3615ms |

## Dimension verification

The new `clipped_text` dimension has three defect fixtures and clean controls
for ellipsis, line-clamp, and scrollable escape affordances. All three expected
findings were observed with no false positive or false negative. Its governed
threshold is `text_clip_tolerance_px`, and the dimension remains `warn` by
default because some interfaces intentionally hide secondary text.

The benchmark also verifies the closed `expect_text` smoke-flow assertion
against visible body text and current input, textarea, or select values. A
mismatch is reported through the dedicated blocking
`smoke_flow_text_assertion_failed` dimension.

## Limits

- The fixtures are authored by the project and can share blind spots with the
  detector authors.
- The full 128-case benchmark is Chromium-only. Firefox and WebKit retain the
  focused real-browser regression suite.
- The safe area is a deterministic geometry simulation, not an emulation of a
  specific physical device.
- Browser text scaling is applied by the audit engine; it is not a native OS or
  assistive-technology text-size test.
- A perfect result means “no regression in this controlled corpus,” not “100%
  accurate on the web.”
