# Agensi Listing Copy

Use this file for the marketplace form. It is not part of the upload ZIP.

## Listing

- **Name:** Web Delivery QA Gate
- **Slug:** `web-delivery-qa-gate`
- **Price:** Free
- **Category:** Testing & Debugging
- **Requires:** Python 3.10+, Playwright, Chromium
- **External access:** `ego-webqa` CLI or MCP server
- **Repository:** <https://github.com/ROY32172310/qa>
- **PyPI:** <https://pypi.org/project/ego-webqa/>

## Short description

Catch obvious mobile-layout, runtime, resource, and CTA delivery failures in an
AI-generated page with deterministic browser evidence.

## What it does

Web Delivery QA Gate tells an AI agent how and when to run the open-source
`ego-webqa` audit after generating or changing a web page.

The downloadable ZIP contains the `SKILL.md`, a local MCP configuration
template, setup instructions, the report contract reference, and a worked
mobile-checkout example. The MCP server runs in the buyer's environment;
Agensi does not host it.

The audit opens the rendered page in Playwright, runs a compact mobile viewport
matrix, and returns structured evidence for:

- horizontal overflow and advisory detection of text cut off by an overflow
  boundary without an ellipsis, line clamp, or scroll affordance;
- blank or nearly blank pages;
- JavaScript errors and failed resources;
- unreadably small text and undersized touch targets;
- fixed overlays and bottom safe-area penetration;
- a primary-CTA click with an optional explicit success selector or URL;
- severe layout shift and a small, closed set of related delivery checks.

Every blocking finding includes a selector, the triggering viewport
combination, a repair direction, and a reproduction command. The agent can fix
the issue and rerun the same gate.

The 0.8 integration surface includes a four-variant `quick` preset for repair
loops, bounded named client-side flows, baseline/delta gating for new blocking
regressions, a runtime `doctor`, privacy-first feedback bundles, and versioned
`1.0` JSON Schemas for machine integrations. The default full audit remains the
eight-variant mobile matrix.

## Why use this skill

An agent can generate code that compiles and still deliver a page that overflows
on a phone, throws a runtime error, or has a CTA that does nothing. Static source
inspection and screenshot-only review miss those facts.

This Skill connects the agent to a deterministic, open-source check instead of
inventing another prompt-only QA checklist. Its dimensions and exit codes are
stable, and it produces machine-readable evidence rather than an opinion about
whether the page "looks good".

## Requirements

The software runs locally in the buyer's agent environment. Agensi does not
host or execute the external MCP server.

```bash
python -m pip install "ego-webqa==0.8.2"
ego-webqa setup
ego-webqa --version
```

Firefox and WebKit preview engines are optional:

```bash
ego-webqa setup --browser-engine firefox
ego-webqa setup --browser-engine webkit
```

## Example request

> I just changed this checkout page. Audit `https://example.com/checkout` on
> mobile before calling it done. Check that the primary Buy button reaches the
> confirmation state, fix blocking findings, and rerun until the gate passes.

## Known limitations

- Checks delivery usability, not whether the business flow is correct.
- Does not certify WCAG compliance or perform a security audit.
- Does not maintain visual baselines or replace E2E tests.
- Playwright WebKit is a Safari-engine approximation, not real-device Safari.
- Safe smoke mode blocks requests made by the post-load CTA interaction. A live
  side effect requires explicit user approval.
- The buyer must install Python, Playwright, Chromium, and the `ego-webqa`
  package or configure its MCP server.

## Tags

`playwright`, `browser-testing`, `web-qa`, `frontend`, `delivery-gate`,
`ai-generated`, `agent-verification`
