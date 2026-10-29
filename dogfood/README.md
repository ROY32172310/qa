# Real-world dogfood sample

This directory records a fixed sample of Ego-owned production pages and
canonical generated artifacts. Its purpose is to measure whether `ego-webqa`
finds actionable delivery defects on real pages before the detector registry is
expanded.

The sample deliberately excludes:

- `.ego_memory/snapshots` and other historical editor states;
- placeholder-only templates;
- duplicate hashed generations when a canonical work exists;
- URLs that require credentials or trigger purchases.

## Run

```bash
export EGO_ROOT=/srv/projects/ego
export EGO_PROJECT_SPACE=/data/projects/ego/workspace
python dogfood/run.py
```

The runner invokes the public `ego_webqa` CLI, records wall time, exit code,
report status, issue counts, finding IDs, and the exact non-secret command. By
default, every case disables CTA smoke so this pass measures rendering and
layout evidence only. Dynamic pages may make backend requests unavailable; each
case note identifies that caveat.

Each case has a 180-second deadline by default. Override it with
`--case-timeout-ms`; a timeout is recorded as an incomplete run and does not
prevent the remaining sample from executing.

Evidence is written under `dogfood-results/<timestamp>/` and is ignored by Git:

```text
dogfood-results/<timestamp>/
├── result.json
├── summary.md
└── cases/<case-id>/
    ├── report.json
    ├── agent_summary.json
    ├── junit.xml
    ├── report.sarif
    └── screenshots/
```

## Review protocol

1. Inspect every finding's Agent summary, selector, trigger, and screenshot.
2. Label it `TP` only when it would affect delivery; label environment-only
   failures `FP` and record the cause.
3. Inspect the rendered page independently for obvious breakage not reported by
   the tool; record each miss as `FN`. A clean report is not proof by itself.
4. Record whether the repair suggestion is specific enough for an Agent to act
   on, and whether a second run confirms the repair.
5. Report P50/P95 runtime from serial execution. Parallel runs are throughput
   evidence, not latency evidence.

Ground truth is manually established from the page and screenshot evidence. The
runner only collects observations; it does not label real-world findings.
