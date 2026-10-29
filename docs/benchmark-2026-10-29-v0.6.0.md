# Public benchmark baseline — ego-webqa 0.6.0

This baseline confirms that governed value overrides did not change the default
detector corpus or the Chromium execution baseline. The audit implementation,
suite, and browser remain directly comparable with the 0.5.0 baseline.

## Environment

| Item | Value |
|---|---|
| Tool | `ego-webqa 0.6.0` |
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
| Audit P95 | 1161ms |
| Audit max | 3614ms |

## Governance verification

The release test suite additionally proves that:

- a governed `min_font_px` override changes a real Chromium finding;
- an active `block -> warn` override changes report status and JUnit/SARIF
  severity while preserving the original severity in audit evidence;
- an expired override restores defaults and remains visible in report metadata;
- CLI and MCP consume the same JSON config and produce the same governance
  counts.

## Limits

- The fixtures are authored by the project and can share blind spots with the
  detector authors.
- The full 122-case benchmark is Chromium-only. Firefox and WebKit retain the
  separate focused regression from 0.5.0.
- The safe area is a deterministic geometry simulation, not an emulation of a
  specific physical device.
- Browser text scaling is applied by the audit engine; it is not a native OS or
  assistive-technology text-size test.
- A perfect result means “no regression in this controlled corpus,” not “100%
  accurate on the web.”
