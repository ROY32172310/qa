# Architecture

`ego-webqa` is intentionally split into five core pieces:

1. `config.py`: public configuration and the only threshold source of truth.
2. `probes.py`: browser-side facts, with no pass/fail decisions.
3. `engine.py`: Playwright orchestration and Python-side classification.
4. `reporting.py`: stable JSON, JUnit, and SARIF adapters.
5. `cli.py`: argument handling, local serving, and exit codes.

The core package has one runtime dependency: Playwright. Browser binaries are
installed separately.

## Profiles

`baseline` covers delivery behavior across the configured viewport matrix.
`accessibility` adds deterministic document and interaction checks while
reusing the same browser facts, threshold model, issue model, and reporters.
Profile selection changes the issue rules, not the report schema.

## CI adapter

`action.yml` is a thin composite Action over the CLI. It owns runner setup,
browser installation, and artifact upload; audit policy remains in
`Settings`. Action inputs are passed through environment variables and a Bash
argument array rather than interpolated into an executable script.

## Deliberate exclusions

The core does not know about:

- a deployment service or short-link provider;
- user/work/share identities;
- proprietary product shells;
- miniapp delivery conventions;
- a particular test runner or test-case database.

These can be implemented as external plugins or CI adapters without changing
the deterministic core.

## Compatibility

The JSON report uses `schema_version`. New optional fields may be added inside
the same major schema. Removing or changing existing field semantics requires a
new schema version.
