# Real-site calibration — 2026-10-28

This calibration is a pressure test, not the product benchmark. Mature content
sites intentionally carry ads, analytics, authentication failures, and large
payloads that are outside the primary "AI-generated delivery page" use case.
The purpose was to identify deterministic false positives and strengthen facts
without tuning the product around those sites.

## Observations

| Site | Evidence | Interpretation | Action |
|---|---|---|---|
| Baidu | Page-frame `image` request to `127.0.0.1`; two cross-origin image requests blocked by ORB; three script 403s | The loopback request belongs to the page, but it cannot be used to prove that a local audit failed | Preserve frame, resource type, origin, status, and error evidence |
| Baidu | Fixed slide-out panel at `x=-250` with no viewport intersection | Fully offscreen panel was a false positive caused by using element area instead of visible intersection | Fixed; covered by a browser fixture |
| JD | `xhr`/`script` 403 responses from `api.m.jd.com`; application logs the same transport failures | Authentication and API failure are real facts but must not be merged into one opaque string | Preserve method, type, frame, status, and occurrence count |
| JD | 120px images rendered around 37x35 | Small-image distortion was dominated by CSS pixel rounding | Excluded media below the 48px rendered floor |
| Tencent | Desktop `xhr` request from the public page to `127.0.0.1:11601/check` | Common local-client probe pattern; the evidence, not an automatic blanket ignore, distinguishes it from a local H5 target | Preserve as structured cross-origin evidence |
| Tencent | Mobile cross-origin script blocked by ORB | Browser policy failure can hide a real integration defect | Keep blocking until a controlled model proves otherwise |
| Tencent | 24x19 images rendered at 8x7 | Same small-media rounding false positive as JD | Fixed by the rendered floor |

## Policy retained

- Do not ignore every loopback URL: local pages are a core audit target.
- Do not ignore every ORB or 403 response: both can represent real breakage.
- Do not weaken layout-shift or transfer budgets because mature content sites
  exceed them.
- Treat only fully offscreen overlays and sub-48px aspect drift as detector
  implementation errors; both now have positive and negative browser fixtures.

## Reproduction

The controlled fixtures live in `tests/test_browser_audit.py`:

- `overlay.html` contains one offscreen fixed panel and one viewport-intersecting
  modal.
- `media.html` contains a tiny rounded icon, a severely distorted image, and a
  correctly rendered image.
