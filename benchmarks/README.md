# Public delivery benchmark

This directory is a reproducible regression benchmark for `ego-webqa`. It
contains curated positive and clean-control fixtures, a versioned manifest, a
real-Chromium runner, and an evaluator independent of detector thresholds.

## Run

Install the development environment and Chromium first:

```bash
python -m pip install -e '.[dev]'
python -m playwright install chromium
python benchmarks/run.py
```

The default run expands `suite.json`, starts a local fixture server, executes
122 independent cases serially, and writes:

```text
benchmark-results/<timestamp>/
├── result.json
├── summary.md
└── cases/<case-id>/
    ├── report.json
    └── screenshots/
```

Useful selections:

```bash
python benchmarks/run.py --case primary-cta-dead--mobile
python benchmarks/run.py --tag accessibility
python benchmarks/run.py --jobs 4 --allow-mismatch
```

Serial execution (`--jobs 1`) is the default because latency is part of the
evidence. Parallel runs are useful for throughput, but `result.json` marks
their latency as non-comparable.

Exit code `0` means every expanded case exactly matched its expected issue set
and severity. Exit code `1` means at least one case regressed; exit code `2`
means the suite or invocation is invalid.

## Manifest

`suite.json` defines the viewport variants and expands compact scenarios into
explicit case IDs. Each scenario must declare either `fixture` or `target`,
whether it is a clean control, and the exact expected issue codes:

```json
{
  "id": "primary-cta-dead",
  "fixture": "cta-dead.html",
  "variants": ["narrow", "mobile", "desktop"],
  "expected_issue_codes": ["dead_primary_cta"],
  "expected_clean": false,
  "smoke": true,
  "tags": ["smoke", "blocking"],
  "rationale": "The primary Start button has no handler."
}
```

Rules enforced by the loader:

- every expected/forbidden code must exist in the closed dimension registry;
- an accessibility-only dimension requires the accessibility profile;
- clean controls cannot also declare issue codes;
- every fixture must exist;
- case IDs, expanded IDs, and variants must be unique;
- suite defaults and per-case settings are merged before `Settings` validation.

Use `expected_severities` only when a dimension has runtime-dependent severity,
such as severe versus moderate layout shift. Otherwise the evaluator maps the
registry's `block/warn` default to the report's `error/warning` severity.

## Metrics

The evaluator exposes separate questions so a good-looking aggregate cannot
hide an important failure:

- **Exact matches:** expected code set, observed code set, and severities all
  match, with no runtime error.
- **Case precision/recall/F1:** did the gate identify defective scenarios and
  stay quiet on clean controls?
- **Blocking false-positive rate:** cases with no expected blocking dimension
  that nevertheless emit a blocking finding.
- **Blocking false-negative rate:** cases expecting a blocking dimension that
  emit none.
- **Dimension TP/FP/FN:** per-dimension behavior across every expanded case.
- **Runtime P50/P95/max:** complete `audit()` wall time, including browser and
  artifact overhead.

Unexpected warnings on positive cases still make that case non-exact. This is
intentional: an extra root cause can send an Agent to repair unrelated code.

## Boundaries

The fixtures are synthetic and run only in local Chromium. A perfect result is
not evidence of real-site coverage, browser-engine parity, business
correctness, security, or WCAG conformance. Add adversarial clean controls when
real projects expose a false positive; do not silently duplicate a detector
threshold into the expected result.
