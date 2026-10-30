# Field feedback protocol

The synthetic benchmark protects detector behavior; field feedback decides
which checks deserve broader trust. Record evidence from real pages without
turning the repository into a store of private customer data.

## Record one case

Use an issue with these fields:

| Field | Allowed content |
|---|---|
| Tool version | Exact `ego-webqa --version` output |
| Target class | Public, local-generated, authenticated, or private |
| Browser | Engine and system channel, if relevant |
| Outcome | `actionable-tp`, `valid-fp`, `missed-defect`, or `runtime-failure` |
| Dimension | Registered issue id or `unreported` for a missed defect |
| Reproducibility | One public URL, sanitized generated fixture, or private maintainer reproducer |
| Repair result | Cleared, persisted, accepted exception, or not attempted |
| Bundle | Reviewed `feedback_bundle.json`, when privacy allows |

Do not upload credentials, storage state, signed URLs, private page content, or
an unreviewed full report. A private case may be represented by a minimal
fixture that preserves only the responsible layout or interaction.

## Triage rules

- An `actionable-tp` needs a visible failure, a clear repair, and a successful
  or explicitly abandoned rerun.
- A `valid-fp` needs an explanation of why the rendered page remains usable
  plus an identifying selector or screenshot for private review. It becomes a
  benchmark clean-control candidate before any threshold changes.
- A `missed-defect` needs a visible failure and the viewport or short flow that
  exposes it. Add a closed positive fixture before adding a detector.
- A `runtime-failure` is counted separately from detector precision. Preserve
  the exit code and sanitized terminal tail; do not label the target as broken.

Repeated cases are preferred over one-off requests. A new dimension starts
advisory only after a reproducible failure mode exists; blocking severity
requires a clean control and field evidence that a false negative matters to
delivery.

## Review cadence

Review open feedback weekly while the corpus is small and monthly after the
first 30 cases. Track dimension, target class, outcome, and duplication — not
just issue count. The useful signal is a repeated scenario with a verified
repair, not generic praise or a raw page-view number.
