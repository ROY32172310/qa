# First trial: get a useful result in 15 minutes

This protocol is for a developer who has a generated page, H5 demo, or preview
that is nearly ready to share. The goal is to determine whether `ego-webqa`
finds a concrete delivery defect that the creator can verify and repair, not to
collect a generic satisfaction score.

## What you need

- A web page that already renders in Chromium.
- A public preview URL or a local static build.
- Permission to inspect the generated page and its browser console.
- About 15 minutes, including browser installation.

Do not provide credentials, signed query strings, private page content, or an
unreviewed full report in a public issue.

## 1. Run the published package

```bash
python -m pip install ego-webqa
python -m playwright install chromium
ego-webqa https://your-preview.example --out .qa/first-trial
```

For a local static build:

```bash
ego-webqa --dir ./dist --file index.html --out .qa/first-trial
```

The run writes `agent_summary.json`, `report.json`, JUnit, SARIF, and
screenshots. Exit code `0` means pass or warnings only; `1` means at least one
blocking delivery defect; `2` means the audit could not run.

## 2. Check the first blocking item

Open `agent_summary.json` and choose one item with severity `block`.

Confirm these fields are actionable:

- `dimension_id` tells you which deterministic rule fired.
- `selector` identifies the affected area.
- `trigger` lists the viewport combinations that exposed it.
- `problem` states the measured fact.
- `suggestion` gives a repair direction.
- `reproduce` gives a narrower command.

Inspect the referenced screenshot and page. If the observation matches the
rendered result, make one focused repair and rerun. Do not change multiple
unrelated items at once.

## 3. Record the outcome

Use one of these labels for the first blocking item:

| Outcome | Meaning |
|---|---|
| `actionable-tp` | The finding was real and the repair was clear. |
| `valid-fp` | The page is usable as rendered and the detector should not block it. |
| `missed-defect` | You can see an obvious delivery failure that the run did not report. |
| `runtime-failure` | The browser or audit failed before producing a usable decision. |

For `actionable-tp`, record the dimension, time to repair, and whether the
rerun cleared the blocking status.

For `valid-fp`, include a sanitized screenshot and explain why the rendered
page remains usable. For `missed-defect`, describe the visible failure and the
viewport or interaction that reveals it. For `runtime-failure`, include the
exit code and sanitized terminal tail.

## 4. Send structured feedback

Open the
[result feedback form](https://github.com/ROY32172310/qa/issues/new?template=result-feedback.yml)
and include only:

- the `ego-webqa --version` output;
- the target type;
- the sanitized command or config;
- the relevant Agent summary item;
- the expected result and why.

The evidence board is useful as a reference for the expected
before/after shape:
<https://roy32172310.github.io/qa/>.

## What counts as a successful first trial

A successful trial does not require a clean page. It requires a trustworthy
loop: the tool reports a concrete observation, the developer can verify it,
and a focused repair produces a predictable second result. One verified
actionable finding is more useful than a long list the developer cannot trust.
