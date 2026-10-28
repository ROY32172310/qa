# ego-webqa

Deterministic delivery QA for AI-generated web pages, H5 demos, and PWAs.

Point it at a URL. It opens the page in a real Chromium browser, checks a
mobile/tablet/desktop matrix, safely probes the primary call to action, and
leaves screenshots plus machine-readable evidence behind.

## Why

Generated pages often pass unit tests while still shipping obvious delivery
defects: content wider than the phone, invisible buttons, broken images,
console errors, a call-to-action that does nothing, or a page that shifts while
the user is trying to tap it.

`ego-webqa` turns those into deterministic checks. It is not a visual-regression
service and does not require writing tests or storing approved screenshots.

## Install

After v0.2.0 is published, install it from PyPI:

```bash
python -m pip install ego-webqa
python -m playwright install chromium
```

To install the current checkout before a release:

```bash
git clone https://github.com/ROY32172310/qa.git
cd qa
python -m pip install .
python -m playwright install chromium
```

For development, use `python -m pip install -e '.[dev]'`.

Use a system Chrome instead of downloading Chromium:

```bash
ego-webqa https://example.com --browser-channel chrome
```

## Use

```bash
ego-webqa https://example.com
ego-webqa --dir ./dist --file index.html
ego-webqa http://127.0.0.1:8000 --viewports 390x844,768x1024,1440x900
ego-webqa https://example.com --ready-selector "#app-ready" --wait-for-network-idle
ego-webqa https://example.com --smoke-success-selector "#thank-you"
ego-webqa https://example.com --profile accessibility
```

Exit codes:

- `0`: pass or warnings only
- `1`: at least one blocking error
- `2`: invalid invocation or browser/runtime failure

Every run writes:

```text
webqa-report/
├── report.json
├── junit.xml
├── report.sarif
└── screenshots/
```

Add `--fail-on-warn` for CI gates that require a completely clean report.

## Checks

Blocking errors:

- horizontal page overflow
- JavaScript page errors and `console.error`
- failed resources and HTTP errors
- a nearly blank page
- unreadable text below 10px
- broken visible images
- distorted canvas/image/video aspect ratio
- dead primary CTA
- severe unexpected layout shift

Warnings:

- small hit targets below 44px
- secondary text below 12px
- oversized fixed overlays
- slow first contentful paint
- moderate layout shift
- excessive first-load bytes or request count

The browser probe reports facts. All thresholds and pass/fail decisions live in
[`src/ego_webqa/config.py`](src/ego_webqa/config.py).

### Profiles

`baseline` is the default delivery profile. It checks whether the page renders,
responds, fits the viewport, and lets the primary action work.

`accessibility` keeps every baseline check and adds deterministic checks for:

- missing document language or page title
- controls without an accessible name
- visible images without an `alt` attribute
- interactive content inside `aria-hidden` containers
- duplicate IDs and skipped heading levels
- positive `tabindex` values that override the natural focus order

This profile catches common machine-detectable defects. It is not a WCAG
conformance audit or a replacement for keyboard and assistive-technology
testing.

## Configuration

```bash
ego-webqa https://example.com --config examples/webqa.json
```

```json
{
  "profile": "accessibility",
  "viewports": ["390x844:mobile", "768x1024:tablet", "1280x800:desktop"],
  "min_tap_target_px": 44,
  "min_font_px": 12,
  "ready_selector": "#app-ready",
  "wait_for_network_idle": true,
  "smoke_mode": "safe",
  "smoke_success_selector": "#thank-you",
  "smoke_success_url_pattern": "/complete$",
  "ignore_selectors": [".third-party-chat-widget"],
  "ignore_console_patterns": ["third-party-widget"],
  "ignore_request_patterns": ["/analytics/"]
}
```

Use `--smoke-selector "#checkout"` when the primary action's text is not matched
by the default CTA vocabulary. Safe smoke aborts HTTP requests and switches the
isolated browser context offline after the initial load. Use `--smoke-mode live`
only when real side effects are intended, or `--no-smoke` when even a DOM-only
click is undesirable.

`smoke_success_selector` and `smoke_success_url_pattern` replace the generic
"something changed" heuristic with an explicit post-click contract. When both
are configured, both must change from unmatched to matched.

Use `ready_selector` for SPA content that appears after the load event. Known
third-party console and request noise can be excluded with regex patterns
without hiding DOM-based findings.

## GitHub Actions

This repository is also a composite GitHub Action. The Action installs the
package from the Action ref, installs Chromium, runs the audit, and uploads the
report even when the audit fails:

```yaml
jobs:
  delivery-qa:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ROY32172310/qa@v0.2.0
        with:
          url: ${{ vars.PREVIEW_URL }}
          profile: accessibility
          fail-on-warn: "true"
          artifact-name: webqa-${{ github.run_id }}
```

For a local checkout of this repository, use `uses: ./` after checkout. The
Action's `safe` smoke mode is the default; set `smoke-mode: live` only when the
click is intentionally allowed to cause real side effects. See
[`examples/github-action.yml`](examples/github-action.yml) and
[`action.yml`](action.yml) for the full input set.

The `@v0.2.0` ref becomes available after that tag is pushed. Until the release
tag exists, consume the current branch or a commit SHA.

## Python API

```python
from ego_webqa import Settings, audit

report = audit("https://example.com", settings=Settings(), output_dir="qa")
print(report.status)
```

## Scope and independence

This repository is a standalone extraction of the general-purpose delivery
checks originally proven inside the ego project. It has no dependency on
`ego_protocol`, `ego_uri`, ego sharing, deployment, miniapp, or product-shell
semantics. Product-specific checks belong in plugins, not in the core.

## Development

```bash
python -m pip install -e '.[dev]'
python -m playwright install chromium
pytest
ruff check .
black --check .
mypy
```

See [CONTRIBUTING.md](CONTRIBUTING.md) before adding a rule. Every rule needs a
positive control and an observed failure mode.

## License

MIT
