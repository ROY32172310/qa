# Upstream generated-footer repair verification

## Scope

This pass verifies the Ego generator repair requested by
`docs/generated-footer-repair-brief-2026-10-31.md`. It does not change
`ego-webqa` dimensions, thresholds, severities, or the fixed 20-page historical
corpus.

The repaired Ego commit is
`ego_devloop@8c1d0f1` (`fix(shell): keep footer actions inside narrow viewports`).

## Generator changes

- Footer actions wrap when a narrow viewport or enlarged text makes one row
  exceed the available width.
- Phone-width shells keep the Ego brand icon and hide only the brand text, so
  action labels retain the available width.
- Footer actions are capped at the container width instead of relying on
  viewport clipping.
- Local project previews no longer register `/sw.js`; registration is limited
  to the shared delivery shape `/share/<work>.html`, where that asset exists.
- The footer remains an application-layout item rather than returning to a
  fixed overlay.

No QA detector or threshold was relaxed.

## Focused regression

The shared-shell and PWA regression set passed:

```text
132 passed in 13.68s
Black: passed
Ruff: passed
```

The new browser cases cover both 360x800 and 390x844 at 1.0x and 1.5x text
scale. They assert that:

- the document does not become wider than the viewport;
- every visible footer action remains inside the viewport;
- every visible footer action keeps a hit area of at least 44px;
- the phone-width brand text is hidden while the icon remains.

## Black-box QA evidence

Three freshly assembled pages used the repaired shell with the default
eight-viewport `baseline` matrix:

| Page | Result | Errors | Warnings | Duration |
|---|---|---:|---:|---:|
| Minimal generated shell with footer controls | pass | 0 | 0 | 2,118 ms |
| Real accounting project, regenerated in a temporary copy | pass | 0 | 0 | 2,182 ms |
| Real vocabulary project, regenerated in a temporary copy | pass | 0 | 0 | 2,188 ms |

For comparison, the historical local artifacts in the fixed corpus reported:

- accounting: 2 errors and 4 warnings;
- vocabulary: 10 errors and 6 warnings.

The vocabulary console 404 is absent after the service-worker registration
scope fix.

## Boundary

This proves that newly assembled pages use a repaired shell and pass the same
QA rules. It does not prove that historical public artifacts are already
repaired:

- public `/share/*` pages remain old until they are regenerated and deployed;
- historical benchmark snapshots remain unchanged evidence;
- the 20-page aggregate should be rerun after the platform rollout, not
  retroactively relabelled.

The next acceptance step is to regenerate and publish a representative batch,
then rerun the identical corpus. The external seed-page evidence remains a
separate requirement before treating the unreleased profile split as a market
release.
