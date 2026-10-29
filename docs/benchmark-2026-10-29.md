# Public benchmark baseline — 2026-10-29

This is the first complete run of the public `ego-webqa` delivery benchmark.
It measures detector correctness and complete audit latency on controlled local
fixtures; it is not a real-site survey.

## Environment

| Item | Value |
|---|---|
| Tool | `ego-webqa 0.3.1` |
| Browser | Bundled Chromium via Playwright `1.62.0` |
| Python | `3.11.16` |
| Platform | Linux x86_64, glibc `2.39` |
| Execution | Serial, `--jobs 1` |
| Suite SHA-256 | `614c04fd63a5517660a06cf78eafafbabb3a368cfcd1977a6151f3a197739d29` |

## Result

| Metric | Result |
|---|---:|
| Expanded cases | 118 |
| Clean controls | 29 |
| Defect cases | 89 |
| Exact matches | 118 / 118 |
| Case precision | 100.00% |
| Case recall | 100.00% |
| Case F1 | 100.00% |
| Blocking false-positive rate | 0.00% |
| Blocking false-negative rate | 0.00% |
| Registered dimensions covered | 34 / 34 |
| Audit P50 | 347ms |
| Audit P95 | 1159ms |
| Audit max | 3587ms |

The four explicit slow cases account for the tail: slow first paint, bounded
network idle, delayed load event, and severe layout shift. Typical cases remain
at a few hundred milliseconds.

## What the first run found

The initial calibration was 101/118 exact. Investigation found:

1. A real accessibility crash: standard explicit `<label>` elements passed
   the array index into a `Set` parameter during accessible-name computation,
   causing a blocking `load_error`. Fixed and covered by a browser regression.
2. Duplicate CTA attribution: a click that threw reported both
   `cta_page_error` and `dead_primary_cta`. The more specific page error now
   stops the generic dead-action classification.
3. Two fixture defects rather than product defects: an existing selector was
   already visible, so the assertion never transitioned, and `height:auto`
   neutralized an intended distortion.
4. A severity/statistics bug in the benchmark itself: registry `block/warn`
   values were compared directly to report `error/warning`. The mapping is now
   explicit and tested.

These findings are why the benchmark treats positive controls, negative
controls, severity, and extra findings separately.

## Coverage

All 34 registered dimensions have an authored positive scenario. The suite also
includes clean controls for responsive layout, correct media, offscreen
overlays, working CTA, passing bounded flows, safe mode, accessibility, and
explicit third-party ignore patterns. Cases are expanded over narrow, mobile,
tablet, and desktop variants where the geometry belongs in that matrix.

## Limits

- The fixtures are authored by the project and can share blind spots with the
  detector authors.
- Chromium is the only rendering engine exercised by this run.
- Browser scaling, reduced motion, keyboard-only behavior, and real assistive
  technology are not covered.
- Mature public sites have authentication, ads, analytics, local-client probes,
  and variable payloads that synthetic fixtures do not represent.
- A 100% result means “no regression in this controlled corpus,” not “100%
  accurate on the web.”

Future real-site false positives and misses should be reduced to a minimal
fixture and added as a clean control or positive case before changing a rule.
