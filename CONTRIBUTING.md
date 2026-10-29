# Contributing

## Rule design

Every check should answer a concrete delivery question and have:

1. a clean positive control;
2. a negative control that reproduces a real failure;
3. a stable, actionable diagnostic;
4. evidence in the JSON report;
5. thresholds in `config.py`, not duplicated inside JavaScript.
6. an entry in the closed `dimensions.py` registry with version and detector
   ownership.
7. a case in `benchmarks/suite.json` with explicit expected dimensions.

New dimensions start as advisory warnings. Promote one to blocking only after
real-site evidence shows its false-positive rate is acceptable. The registry
coverage test must continue to prove that every emitted issue code is
registered.

Do not add checks that depend on one product's DOM class names, deployment
service, user identity, or application framework.

## Development

```bash
python -m pip install -e '.[dev]'
python -m playwright install chromium
pytest
ruff check .
black --check .
mypy
```

Browser tests use a temporary local HTTP server. Do not depend on public sites
in the test suite.

The benchmark is part of the quality contract. `tests/test_benchmark.py` proves
that the suite covers every registered dimension and that metrics distinguish
clean controls, exact matches, extras, misses, and severity errors. A change to
a detector should be checked against the complete local benchmark, not only its
new fixture.

## Pull requests

Describe the user-visible failure the rule catches, include a minimal fixture,
and state what stays out of scope. Avoid rules that only express a visual
preference.
