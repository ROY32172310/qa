# Text-clipping dogfood — 2026-10-30

## Scope

The advisory `clipped_text` detector was exercised against three production
Ego pages with the default mobile matrix:

- `https://egohub.tech/discover`
- `https://works.egohub.tech/share/24a290d0.html`
- `https://egohub.tech/gallery.html`

All three audits completed without a runtime error. This was a rule-calibration
sample, not a precision benchmark over the complete 20-page corpus.

## Result

`clipped_text` appeared in five viewport runs on the vocabulary page and in
neither of the other two pages. The affected root cause was the shared footer
brand container: it uses `overflow: hidden`, and text scaling or the narrower
viewport cuts off part of the "由 Ego 创建" label without an ellipsis or scroll
affordance. The captured screenshots show the incomplete label, so this is a
true positive for the advisory delivery check.

The detector did not report the vocabulary page's normal card layout, the
discovery page's responsive cards, or the gallery's rendered content.

## Boundary decision

The check remains a warning. Some products intentionally hide secondary text
with a wrapper rather than an ellipsis; a warning plus a governed tolerance lets
that pattern be acknowledged without silently turning the rule off. Text inside
an explicit ellipsis, line clamp, or genuinely scrollable container remains a
clean control.
