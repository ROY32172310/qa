# Performance baseline contract

`ego-webqa` has two performance evidence classes. They answer different
questions and must not be merged into one release threshold.

## Controlled local regression baseline

Runner: `benchmarks/run.py`

This profile serves curated fixtures from `127.0.0.1`, runs bundled Chromium,
and executes every expanded case serially by default. It is the only current
source of comparable tool-latency regression evidence.

| Evidence | Latest recorded value |
|---|---:|
| Cases | 128 / 128 exact |
| Registered dimensions covered | 38 / 38 |
| Blocking FP / FN | 0% / 0% |
| Complete audit P50 | 342 ms |
| Complete audit P95 | 1154 ms |
| Complete audit max | 3610 ms |

Evidence:
`benchmark-results/20261030T1127Z-release-0.8.0/result.json`.

Rules:

- Compare serial runs on the same corpus and machine profile.
- Treat `--jobs > 1` as throughput-only; its latency is not comparable.
- Keep deliberate slow-response fixtures in the corpus. They are correctness
  controls, so the max can exceed the ordinary interaction target.
- Do not use this P95 as a promise for uncontrolled public pages.

## Real-world observational profile

Runner: `dogfood/run.py`

This profile audits a fixed mix of production URLs and local generated pages.
Target pages, DNS, TLS, third-party services, and the operator's network all
change outside the tool's control.

The result reports these source groups independently:

- `url`: production pages reached over the public network;
- `local`: generated artifacts served from the operator's machine.

For each group and for the aggregate, retain case count, completed audits,
runtime errors, completion rate, and completed-run P50/P95/max. The historical
0.4.0 sample completed 19 of 20 cases with a completed-run P50/P95/max of
14.25/24.71/24.71 seconds; one 180-second deadline failure remains visible as an
execution error rather than disappearing from a latency percentile.

Rules:

- Use public results to observe deployment reliability, completion rate, and
  slow-network behavior.
- Never gate a release on a direct comparison with the controlled local P95.
- Investigate URL and local groups separately before blaming a detector.
- Report runtime failures before discussing percentiles.

## Selection rule

Use the controlled local baseline to answer “did a code change regress the
tool?” Use the real-world profile to answer “what happens under this observed
network and target mix?” Neither result proves business correctness, visual
design quality, security, or WCAG conformance.
