---
name: web-delivery-qa-gate
description: Run a deterministic browser-based delivery check on a live or local web page after an AI agent claims it is ready. Use for quick mobile-layout, runtime-error, broken-resource, and primary-CTA verification; requires ego-webqa, Python, and Playwright.
---

# Web Delivery QA Gate

Use `ego-webqa` to inspect the rendered page before declaring it delivered. This
is a coarse, deterministic gate for obvious usability failures, not a general
QA platform.

## Preconditions

Do not claim the tool is installed without checking it:

```bash
ego-webqa --version
```

The tested release is `0.7.0`. It requires Python 3.10+ and a compatible
Playwright browser. If the command is missing, explain the dependency and ask
before installing anything:

```bash
python -m pip install "ego-webqa==0.7.0"
python -m playwright install chromium
```

Install Firefox or WebKit only when the user asks for that engine:

```bash
python -m playwright install firefox
python -m playwright install webkit
```

If official `audit_web_page` is already exposed through MCP, prefer that tool.
Otherwise run the CLI. Agensi does not host or run external MCP servers, so the
buyer must have `ego-webqa` available in the agent's execution environment.

## Run the gate

For a live URL:

```bash
ego-webqa "https://example.com" --out .qa/agent-delivery --json
```

For a local page:

```bash
ego-webqa --dir . --file index.html --out .qa/agent-delivery --json
```

Use the default eight-viewport mobile matrix unless the user explicitly asks
for a narrower or broader set. Useful opt-in settings:

```bash
# Wait for an application-ready selector.
ego-webqa "https://example.com" --ready-selector "#app" \
  --out .qa/agent-delivery --json

# Verify a CTA against a concrete success contract.
ego-webqa "https://example.com" \
  --smoke-selector "#buy" \
  --smoke-success-selector "#confirmation" \
  --smoke-require-assertion \
  --out .qa/agent-delivery --json

# Approximate the Safari engine; this is not a real-device Safari test.
ego-webqa "https://example.com" --browser-engine webkit \
  --out .qa/agent-delivery --json
```

Keep safe smoke mode as the default. Use `--smoke-mode live` only after the
user explicitly accepts possible side effects such as a real purchase,
submission, or destructive state change.

If a project config exists, pass it with `--config PATH`. Use config for bounded
smoke flows, authenticated storage state, ignores, or governed threshold
overrides. Do not generate arbitrary JavaScript assertions.

## Interpret and repair

- Exit `0`: no blocking findings; warnings may still exist.
- Exit `1`: at least one blocking delivery finding.
- Exit `2`: invocation or browser/runtime failure, not proof that the target
  page is broken.

Read `agent_summary.json` in the output directory. Fix every blocking finding,
rerun the same command, and continue until exit `0`. Preserve selectors,
viewports, screenshots, and reproduction commands as evidence. Review relevant
warnings, but do not turn unrelated warnings into mandatory work.

The warning-level `clipped_text` finding means visible text is cut off by an
overflow boundary without a recognized ellipsis, line clamp, or scroll
affordance. Repair it when it obscures user-relevant content; do not “fix” a
deliberately hidden secondary label merely to make warnings disappear.

When reporting back, state:

1. the page or file tested and the exact command used;
2. pass/fail plus blocking and warning counts;
3. the highest-impact findings, with selectors or screenshots;
4. what was fixed and the final rerun result;
5. any remaining unverified risk.

## Boundary

This gate does not prove business logic, security, WCAG compliance, visual
regression, cross-browser parity, real-device behavior, or a full user journey.
Do not describe a passing report as proof that the whole product is ready.
