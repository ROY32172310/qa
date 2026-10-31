# Generated-page footer repair brief

## Request

Fix the shared Ego generated-page footer and control row, then rerun the fixed
20-page `baseline` corpus. This is an upstream generator repair, not a QA
threshold change.

The evidence is recorded in
`docs/real-world-triage-2026-10-31-baseline.md`. Eighteen of 20 manually
confirmed baseline root causes belong to the shared footer/control system.

## Observed failures

At 360px and 390px widths, including 1.5x text scale:

- the footer action row extends beyond the viewport;
- action and attribution text is clipped by the viewport edge;
- the fixed footer extends to `bottom: 0` without a safe-area reserve;
- several footer and menu controls are below the 44px target floor.

The existing generated pages commonly use:

```css
.ego-footer {
  position: fixed;
  inset: auto 0 0;
  padding: 8px 16px;
}
```

They do not consistently reserve
`env(safe-area-inset-bottom, 0px)`, reserve equivalent bottom space in the page
layout, or allow the action group to wrap at narrow widths.

## Required behavior

1. The fixed footer and every interactive child stay outside the simulated
   34px bottom safe-area band.
2. Page content remains scrollable above the complete footer height, including
   its safe-area padding.
3. Footer actions do not generate horizontal document overflow at 360px or
   390px with 1.0x or 1.5x text.
4. Footer labels do not clip without an intentional ellipsis or scroll
   affordance.
5. Footer and menu controls expose a hit area of at least 44x44px. A smaller
   visual glyph is acceptable inside the larger hit area.
6. The generated vocabulary page stops requesting a missing service-worker
   script.

## Implementation direction

Use one injected footer implementation rather than copying a large CSS and
markup block into every generated artifact. The layout should:

- include `box-sizing: border-box`;
- apply bottom padding equivalent to
  `max(8px, env(safe-area-inset-bottom, 0px))`;
- reserve matching footer and safe-area height on the page;
- use a responsive grid/flex layout with `min-width: 0` and wrapping;
- give every button and link a minimum 44x44px hit area;
- preserve keyboard focus and readable labels.

Illustrative direction, not a mandate to copy verbatim:

```css
:root {
  --ego-footer-base-pad: 8px;
  --ego-footer-safe-pad: max(
    var(--ego-footer-base-pad),
    env(safe-area-inset-bottom, 0px)
  );
}

.ego-footer {
  position: fixed;
  inset: auto 0 0;
  box-sizing: border-box;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  padding: 8px 16px var(--ego-footer-safe-pad);
}

.ego-footer .actions {
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.ego-footer button,
.ego-footer a[href] {
  min-width: 44px;
  min-height: 44px;
}
```

## Acceptance

Rerun the same manifest without changing thresholds:

```bash
uv run --locked python scripts/dev.py dogfood \
  --ego-root /srv/projects/ego \
  --project-space /data/projects/ego/workspace \
  --profile baseline \
  --out dogfood-results/post-footer-repair
```

Expected result for repaired pages:

- no `bottom_safe_area_penetration`;
- no footer-related `text_scale_layout_break` or `clipped_text`;
- no footer/menu `small_tap_targets`;
- no service-worker `console_error` on the vocabulary artifact;
- no new structural dimensions;
- zero runtime errors.

The discovery-page tagline overflow and compact controls are separate from the
shared footer and require their own repair.
