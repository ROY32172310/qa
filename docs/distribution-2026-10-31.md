# Distribution evidence: Glama auto-sync of ego-webqa 0.8.2

Observed on 2026-10-31 (Asia/Shanghai).

This note records what an external MCP directory observed from the public
repository. It is evidence that the distribution and discovery path is
working. It is not evidence of user adoption, retention, or product-market
fit.

## Verified profile

- Canonical Glama profile:
  <https://glama.ai/mcp/servers/ROY32172310/qa>
- Badge image:
  <https://glama.ai/mcp/servers/ROY32172310/qa/badge>
- The older notification link under `roy-studio/ego-webqa` returned HTTP 404.
  The public profile above is the current canonical slug.
- Glama categories: Testing & QA Tools, Browser Automation, and Developer
  Tools.

## Version synchronization

The profile's Tool Schema Changelog contains:

- `v0.8.2`, one tool update, dated 2026-10-30;
- `v0.4.2`, one tool update, dated 2026-10-29.

The profile also renders the current README's `ego-webqa==0.8.2` installation
examples and `ROY32172310/qa@v0.8.2` GitHub Action example. Glama separately
notified the maintainer that the 0.8.2 build succeeded and was published on
2026-10-30.

Glama's public claim dialog states that it continuously fetches updates from
GitHub. The independently visible 0.8.2 changelog entry, refreshed README
content, and build/release notifications are therefore evidence that Glama's
automatic discovery and refresh path ingested the release without a manual
directory submission for this release.

## Quality signals

At the time of verification:

- The official Glama badge endpoint returned HTTP 200 with `image/png`.
- The 760x400 badge rendered `license A`, `quality A`, and `maintenance A`.
- TDQS rendered `A`, with an overall score of `3.8/5.0`, scored
  2026-10-30 21:10 UTC across the single `audit_web_page` tool.
- The maintenance card showed `Activity: Maintained` and
  `Responsiveness: No issues`.

Glama exposes license, quality, and maintenance as three independent grades.
It does not use a single AAA score. These are Glama directory signals and
should not be presented as security certification or cross-directory
benchmark results.

## TensorBlock and Glama

TensorBlock and Glama are separate discovery channels with different scoring
and metadata models. Both are linked from the repository README. Their signals
must remain separately attributed; a badge from one must not be used as if it
were a rating issued by the other.

## Interpretation boundary

This event establishes:

- external directory discovery of the public GitHub repository;
- automated ingestion of release and tool-schema changes;
- a stable public profile and quality badge URL for continued observation.

It does not establish:

- real user installs or active users;
- retention or task success;
- comparative superiority over another QA product;
- validation of the audit rules against a market-wide corpus.

## Reproduction

```bash
curl -I https://glama.ai/mcp/servers/ROY32172310/qa/badge
curl -o /tmp/ego-webqa-glama-badge.png \
  https://glama.ai/mcp/servers/ROY32172310/qa/badge
```

The first command should return `HTTP/2 200` and `content-type: image/png`.

