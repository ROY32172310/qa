# Changelog

## 0.2.0 - 2026-10-28

- Fix the public SARIF tool URI.
- Declare the formatter and packaging tools used by CI.
- Verify coverage, wheel installation, and package metadata in CI.
- Document source and PyPI installation paths.
- Add tag-triggered PyPI Trusted Publishing.
- Use real mobile browser contexts with touch, mobile user agents, and evidence.
- Make primary-CTA smoke safe by blocking post-load network requests.
- Validate configuration field types and threshold ranges.
- Wait for an optional ready selector or bounded network-idle period.
- Ignore known console and failed-request noise with regex policies.
- Short-circuit secondary findings after a failed main document.
- URL-encode local filenames used by the bundled static server.
- Require explicit selector and URL assertions for CTA success when configured.
- Add an `accessibility` profile for deterministic document, control, image,
  heading, ID, focus-order, and ARIA-hidden checks.
- Add a composite GitHub Action with safe smoke defaults, profile selection,
  browser setup, and always-on report artifact upload.

## 0.1.0 - 2026-10-27

- Initial standalone extraction.
- Multi-viewport Chromium audit.
- Layout, readability, media, network, timing, and primary-CTA checks.
- JSON, JUnit XML, SARIF, and screenshot artifacts.
- Independent JSON configuration and no ego-private dependencies.
