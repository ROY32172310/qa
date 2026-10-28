# Security

## Reporting

Report vulnerabilities privately to `32172310@qq.com`. Do not open a public
issue before a fix is available.

## Runtime model

`ego-webqa` launches a real browser against a target supplied by the caller.
Only audit pages you are authorized to test.

The primary-CTA smoke test uses safe mode by default. It clicks one control
after aborting HTTP requests and switching the isolated browser context offline,
so the click cannot reach the target's API over HTTP or an existing WebSocket.
DOM-only state changes still occur.

Use `--smoke-mode live` only when a real purchase, publication, deletion, or
other external side effect is explicitly intended. Use `--no-smoke` when even a
DOM-only click is undesirable.

The tool does not upload source code or screenshots. Artifacts are written
locally unless the calling CI system uploads them.
