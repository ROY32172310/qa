# Upstream generated-footer rollout: 2026-10-31

## Scope

This record closes the deployment and black-box verification loop for the
generated-page footer repair documented in
`docs/upstream-footer-repair-2026-10-31.md`.

It separates three kinds of evidence:

1. newly regenerated and publicly deployed Ego works;
2. unchanged historical file snapshots in the fixed dogfood corpus;
3. an unrelated public discovery-page defect.

The Ego change remains local to the private ecosystem. No Ego remote
publication is part of this rollout.

## Production rollout

Three representative works were republished through the normal production
writer with main-source `scp` and object-store `cos` shadow writes. Each
preflight reported:

```text
source_equivalent: true
shortlink_policy: preserve
artifact_write_contract: required-shadow
```

| Work | Share URL | Revision | Published HTML SHA-256 |
|---|---|---:|---|
| Tetris | `https://egohub.tech/s/kuf38d` | 4 | `ae2af7f6d0ec3cae65a8a2fa694be8efccc42b6743bf1f476261d87f19428c5a` |
| Word quiz | `https://egohub.tech/s/iikj3c` | 5 | `80ccfb0a0f0235d3a5c4ea2c26fd7ae8309913f86c7fe6157fe121cc2ad79dc0` |
| Vocabulary | `https://egohub.tech/s/8oxegn` | 9 | `d0dfd125bae68211832380f05eb1ce318fddf7e8fe14768846f6669058433f59` |

Recoverable pre-publication backups:

```text
/data/projects/ego/var/backup/republish-existing/7ce6e45e-20261031-173948
/data/projects/ego/var/backup/republish-existing/9a3061bc-20261031-173912
/data/projects/ego/var/backup/republish-existing/24a290d0-20261031-173814
```

## Production verification

A direct HTTP check of all three `works.egohub.tech/share/*.html` objects
returned `HTTP/2 200`, `x-ego-artifact: hit`, and
`x-ego-artifact-source: cos`. The returned `x-ego-artifact-sha256` values
exactly matched the table above.

Each production page was then audited as a black box with the default
eight-viewport `baseline` matrix and real Chrome:

| Page | Result | Errors | Warnings | Duration |
|---|---|---:|---:|---:|
| Tetris | pass | 0 | 0 | 21,989 ms |
| Word quiz | pass | 0 | 0 | 16,246 ms |
| Vocabulary | pass | 0 | 0 | 16,644 ms |

Evidence directories:

```text
/tmp/ego-webqa-live-7ce-20261031/
/tmp/ego-webqa-live-9a3061bc-20261031/
/tmp/ego-webqa-live-24a290d0-20261031/
```

## Fixed corpus rerun

The same fixed 20-page manifest was rerun after the rollout:

```text
manifest SHA-256: 6c944bdff481981e621379118df567ac7d26898a5e42bfd6f78106e6e1f964e9
profile: baseline
browser: system Chrome
successful audits: 20/20
runtime errors: 0
```

Primary evidence:

```text
dogfood-results/20261031-post-footer-repair/result.json
```

The three republished public works all changed from `fail` to `pass`:

| Page | Before | After |
|---|---|---|
| `egohub-work-tetris` | fail, 8 occurrences | pass, 0 occurrences |
| `egohub-work-word-quiz` | fail, 8 occurrences | pass, 0 occurrences |
| `egohub-work-vocabulary` | fail, 8 occurrences | pass, 0 occurrences |

The entire fixed corpus changed as follows:

| Metric | Before | After |
|---|---:|---:|
| Pass | 10 | 13 |
| Warn | 0 | 1 |
| Fail | 10 | 6 |
| Issue occurrences | 86 | 60 |
| Repair items | 20 | 13 |
| Runtime errors | 0 | 0 |

The post-rollout aggregate contains:

```text
bottom_safe_area_penetration: 4
clipped_text: 2
console_error: 1
small_tap_targets: 4
text_scale_layout_break: 2
```

This comparison is not a single-variable causal experiment: the earlier
baseline record used Playwright's default Chromium while this rerun used the
system Chrome channel. The unchanged manifest, page inventory, profile, and
viewports make the result useful rollout evidence, but the 86-to-60 difference
must not be presented as a controlled effect size or a market-wide
false-positive rate.

## Remaining corpus findings

Seven pages still produce at least a warning:

| Page | Status | Occurrences | Classification |
|---|---|---:|---|
| `egohub-discover` | fail | 8 | Independent discovery-page tagline overflow and compact-control findings |
| `ego-generated-accounting` | warn | 4 | Historical file snapshot; only `clipped_text` remains |
| `ego-generated-vocabulary` | fail | 16 | Historical file snapshot with the old service worker and footer |
| `ego-public-math-practice` | fail | 8 | Historical file-backed public snapshot with safe-area and tap-target findings |
| `ego-generated-noodle-shop` | fail | 12 | Historical file snapshot with safe-area and tap-target findings |
| `ego-generated-click-counter` | fail | 4 | Historical file snapshot with a safe-area finding |
| `ego-generated-games-gallery` | fail | 8 | Historical file snapshot with safe-area and tap-target findings |

Five failing file-backed cases were not regenerated or substituted during this
rollout. Their findings therefore continue to describe the historical
artifacts, not a failure of the newly deployed footer. `ego-generated-accounting`
is also a historical snapshot; the reduced warning demonstrates that its
remaining text-clipping finding must be triaged separately rather than folded
into the deployed-footer claim.

## CI and boundary

QA commit `5f290b5` passed GitHub Actions run
`https://github.com/ROY32172310/qa/actions/runs/41189429601` across all ten
jobs: six OS/Python test jobs, benchmark, cross-browser, Action smoke, and
package.

This evidence proves that three newly regenerated public works deploy the
repaired shell and pass the same black-box QA rules. It does not prove that all
historical artifacts are repaired, and it does not replace external
AI-generated page samples. The profile-split candidate remains without a
package release until that external evidence exists.
