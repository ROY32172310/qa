# Agent working agreement

This repository is a deterministic delivery gate for AI-generated web pages.
Optimize for trustworthy, reproducible evidence rather than feature count.

## Read before changing behavior

Read the relevant sections of:

- `README.md` for the public product contract and boundaries;
- `docs/architecture.md` for component ownership and data flow;
- `docs/json-contracts.md` before changing report payloads;
- `docs/field-feedback.md` before adding or promoting a detector;
- `docs/releasing.md` before preparing a release;
- `CHANGELOG.md` for the current unreleased work.

## Non-negotiable boundaries

- The tool performs deterministic coarse delivery QA. Do not turn it into a
  general E2E framework, visual-regression service, security scanner, or WCAG
  certification product.
- Detector decisions and thresholds belong in the closed registry and Python
  code. Do not accept arbitrary user JavaScript or arbitrary assertions.
- A new issue dimension starts advisory. Promote it to blocking only with a
  positive fixture, a clean control, and evidence that the failure matters.
- Keep the public `1.0` JSON contract backward compatible. Adding optional
  fields is allowed; silently changing required fields is not.
- Reports and feedback bundles must remain privacy-safe by default. Do not add
  target URLs, page text, selectors, paths, credentials, or configuration to
  the default feedback projection.
- Preserve the safe smoke-flow boundary: closed actions, bounded length, no
  arbitrary code, and explicit post-action evidence.

## Development loop

1. Inspect `git status` and preserve unrelated worktree changes.
2. State the user-visible failure or contract being changed.
3. Make the smallest scoped implementation change.
4. Run the narrowest relevant tests first.
5. Run the complete local gate before claiming completion:

   ```bash
   .venv/bin/python scripts/dev.py full
   ```

6. For detector, probe, or rule changes, run the real-page corpus and classify
   results before changing thresholds:

   ```bash
   .venv/bin/python scripts/dev.py dogfood \
     --ego-root /srv/projects/ego \
     --project-space /srv/ego/ego_project_space \
     --out dogfood-results/<dated-run>
   ```

7. Update `CHANGELOG.md` and any affected contract, architecture, or field
   evidence document.
8. Commit only files in scope, push, and verify the resulting GitHub Actions
   run. A local pass is not a substitute for the cross-platform CI result.

Generated `test-results/`, `benchmark-results/`, and `dogfood-results/` are
evidence inputs, not tracked source. Summarize durable conclusions under
`docs/` instead of committing raw private or environment-specific artifacts.

## Evidence standard

A completion claim needs the relevant observable proof:

- tests report the exact pass/fail count and coverage when coverage changed;
- benchmark changes report exact matches plus false-positive and false-negative
  counts;
- real-page changes separate structural findings from transient timing noise;
- packaging and release changes verify the produced artifact, not only source;
- published releases verify GitHub, PyPI, and MCP Registry state as applicable.

Never call an unverified change complete. Distinguish execution failure from a
page defect, and classify findings as `actionable-tp`, `valid-fp`,
`missed-defect`, or `runtime-failure` using `docs/field-feedback.md`.

## When adding a detector or locator

First prove the failure on a sanitized fixture or public URL. Then add:

1. a positive fixture that isolates the failure;
2. a clean control that should remain silent;
3. an assertion for the registered issue code, severity, and actionable
   evidence;
4. benchmark coverage when behavior changes;
5. real-page triage before any blocking-severity change.

Repair addressability is part of detector quality. Prefer a concrete selector,
measurement, trigger, and reproduction command over a technically true but
unactionable page-level message.

## Versioning and release

Do not bump versions after every small change. Batch coherent user-visible work
under `## Unreleased`, then follow `docs/releasing.md`.

Before tagging, keep every release identity synchronized, including:

- `pyproject.toml`;
- `src/ego_webqa/__init__.py`;
- `server.json`;
- the release notes and changelog.

Push the reviewed commit, let CI pass, then create and push the annotated tag.
Verify the release workflow and all publication targets before reporting the
release as available.
