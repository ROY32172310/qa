# JSON integration contracts

`ego-webqa` publishes eight Draft 2020-12 JSON Schemas with the Python package.
They are the executable form of the `1.0` integration contract:

| Name | Output |
|---|---|
| `report` | `report.json` and `--json` |
| `agent-summary` | `agent_summary.json` and MCP structured findings |
| `dimensions` | `--list-dimensions` |
| `feedback-bundle` | `feedback_bundle.json` |
| `delta` | `delta.json` |
| `doctor` | `doctor --json` |
| `browser-install` | `install-browser --json` |
| `setup` | `setup --json` |

Print any schema from an installation:

```bash
ego-webqa --print-schema report
ego-webqa --print-schema agent-summary
```

The schema files are also available under
`src/ego_webqa/schemas/` and as package data in wheels. Consumers should
validate the payload they actually receive instead of inferring compatibility
from the package version alone.

## Evolution policy

- `schema_version` identifies the compatibility contract, not the package
  release. The current contract is `1.0`.
- New optional fields may be added within `1.0`; consumers must ignore fields
  they do not understand.
- A field may be marked deprecated in docs and changelog while remaining
  present and semantically unchanged for at least two minor releases.
- A schema field marked `"deprecated": true` must carry
  `x-ego-webqa-deprecation` metadata with `deprecated_in` and
  `remove_no_earlier_than`; CI enforces the two-minor-release window.
- Removing a required field, changing its type or meaning, changing an enum
  value's meaning, or changing exit-code semantics requires a new schema major.
- New issue dimensions do not require a schema major because `dimensions` is a
  closed registry and issue codes are strings in the transport schema.
- JUnit, SARIF, screenshots, and browser internals are derived or diagnostic
  artifacts; their third-party schemas are not redefined here.

## Integration matrix

| Surface | Report | Agent summary | Dimensions | Feedback | Delta | Doctor | Browser install | Setup |
|---|---|---|---|---|---|---|---|---|
| CLI / `--json` | yes | written | query | subcommand | subcommand | subcommand | subcommand | subcommand |
| MCP | structured | structured | tool schema | no | no | no | no | no |
| GitHub Action | artifact | artifact | artifact | artifact | optional | no | internal | internal |
| Python API | `AuditReport` | builder | registry | builder | comparison | collector | installer | setup |

The CLI, MCP server, and GitHub Action call the same audit engine and report
builder. Integration tests validate shared configuration behavior and generated
payloads; compatibility does not depend on which entry point produced them.

## Compatibility evidence

The repository keeps frozen minimal `1.0` payloads under
`tests/fixtures/contracts/v1.0/`. CI validates all eight payloads against the
packaged schemas, validates actual CLI and MCP output, and checks that the
GitHub Action summary consumes schema-valid feedback and delta documents.

The installed-wheel job prints every packaged schema from the wheel rather than
testing source-tree files. This catches both contract drift and missing schema
package data.

## Scope

Schema validity proves structure and type compatibility. It does not prove that
every dimension fired correctly, that a target is reachable, that a browser is
installed, or that the page satisfies business, security, or WCAG requirements.
