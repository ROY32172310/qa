# Worked example: mobile checkout delivery gate

This is a representative workflow built from the public `agent-summary` `1.0`
contract. The values below illustrate how an agent should consume and act on
the result; they are not a claim about a third-party page.

## Request

```text
Audit https://preview.example/checkout on mobile before calling this change
delivered. Check that the Buy button reaches the order-confirmation state, fix
blocking findings, and rerun the same gate.
```

## First run

Send the `audit_web_page` arguments in `mcp-request.json`. The quick preset
keeps the repair loop short while still varying width, text scale, and safe
area. `smoke_require_assertion` makes the CTA check require the explicit
confirmation selector rather than accepting any incidental DOM change.

The first run returns a blocking page result. A representative excerpt from
`agent_summary.json` is in `expected-agent-summary.json`:

```text
status: fail
dimension: horizontal_overflow
selector: .order-summary
trigger: 360px + 1.5x text scale + safe-area 0
problem: Content extends beyond the viewport width.
suggestion: Allow the summary row to wrap and constrain its minimum width.
```

The agent should inspect the referenced evidence, repair the layout, and rerun
the same request. A CTA-specific failure uses a separate `smoke_flow_*`
dimension and includes the failed step rather than copying a filled password or
other field value into the report.

## Repair

A suitable repair is project-specific. For this example, let the price label
wrap, remove the fixed child width, and keep the total row inside the container:

```css
.order-summary {
  min-width: 0;
}

.order-summary__row {
  flex-wrap: wrap;
}
```

Do not suppress the check or downgrade its severity merely to get a pass. Use a
governed override only when the visual treatment is intentional and the reason,
owner, and expiry are recorded.

## Final run

Rerun with the default full matrix before the final delivery claim:

```text
audit_web_page({
  "url": "https://preview.example/checkout",
  "out_dir": ".qa/checkout-final",
  "smoke_selector": "#buy-now",
  "smoke_success_selector": "#order-confirmation",
  "smoke_require_assertion": true
})
```

Expected delivery result:

```text
status: pass
total_block: 0
CTA: #buy-now reached #order-confirmation
```

The agent should report the tested URL, blocking/warning counts, the repaired
root causes, and any remaining unverified risk. A pass is not proof of business
logic, security, WCAG compliance, visual regression, or every device/browser.
