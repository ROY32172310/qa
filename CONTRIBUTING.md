# Contributing

## Rule design

Every check should answer a concrete delivery question and have:

1. a clean positive control;
2. a negative control that reproduces a real failure;
3. a stable, actionable diagnostic;
4. evidence in the JSON report;
5. thresholds in `config.py`, not duplicated inside JavaScript.

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

## Pull requests

Describe the user-visible failure the rule catches, include a minimal fixture,
and state what stays out of scope. Avoid rules that only express a visual
preference.

