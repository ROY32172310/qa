# ego-webqa

Deterministic delivery QA for AI-generated web pages, H5 demos, and PWAs.

Point it at a URL. It opens the page in a real Chromium browser, checks a
mobile/tablet/desktop matrix, clicks the primary call to action, and leaves
screenshots plus machine-readable evidence behind.

## Why

Generated pages often pass unit tests while still shipping obvious delivery
defects: content wider than the phone, invisible buttons, broken images,
console errors, a call-to-action that does nothing, or a page that shifts while
the user is trying to tap it.

`ego-webqa` turns those into deterministic checks. It is not a visual-regression
service and does not require writing tests or storing approved screenshots.

## Install

```bash
python -m pip install ego-webqa
python -m playwright install chromium
```

Use a system Chrome instead of downloading Chromium:

```bash
ego-webqa https://example.com --browser-channel chrome
```

## Use

```bash
ego-webqa https://example.com
ego-webqa --dir ./dist --file index.html
ego-webqa http://127.0.0.1:8000 --viewports 390x844,768x1024,1440x900
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

## Configuration

```bash
ego-webqa https://example.com --config examples/webqa.json
```

```json
{
  "viewports": ["390x844:mobile", "768x1024:tablet", "1280x800:desktop"],
  "min_tap_target_px": 44,
  "min_font_px": 12,
  "ignore_selectors": [".third-party-chat-widget"]
}
```

Use `--smoke-selector "#checkout"` when the primary action's text is not matched
by the default CTA vocabulary. Use `--no-smoke` for pages where even a click is
not safe.

## GitHub Actions

```yaml
- uses: actions/setup-python@v5
  with:
    python-version: "3.12"
- run: |
    pip install ego-webqa
    python -m playwright install --with-deps chromium
    ego-webqa "$PREVIEW_URL" --out webqa-report
- uses: actions/upload-artifact@v4
  if: always()
  with:
    name: webqa-report
    path: webqa-report/
```

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

