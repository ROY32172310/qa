# Security

## Reporting

Report vulnerabilities privately to `32172310@qq.com`. Do not open a public
issue before a fix is available.

## Runtime model

`ego-webqa` launches a real browser against a target supplied by the caller.
Only audit pages you are authorized to test.

The primary-CTA smoke test clicks one control by default. Use `--no-smoke` on
pages where a click can make a purchase, publish content, delete data, or
otherwise change external state.

The tool does not upload source code or screenshots. Artifacts are written
locally unless the calling CI system uploads them.

