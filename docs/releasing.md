# Releasing

Releases use PyPI Trusted Publishing and MCP Registry GitHub OIDC. No package
publishing token is stored in GitHub. The PyPI publisher is active, not pending.

## One-time setup

1. In GitHub, create an environment named `pypi`.
2. In PyPI, add a trusted publisher for:
   - project: `ego-webqa`
   - owner: `ROY32172310`
   - repository: `qa`
   - workflow: `release.yml`
   - environment: `pypi`

## Publish a version

1. Set the same version in `pyproject.toml` and
   `src/ego_webqa/__init__.py`.
2. Update `CHANGELOG.md`.
3. Set the same version in `server.json` and the project version checks keep it
   synchronized with `pyproject.toml`.
4. Land the release commit on `master` and wait for CI to pass.
5. Create and push an annotated tag:

   ```bash
   git tag -a v0.8.2 -m "ego-webqa 0.8.2"
   git push github v0.8.2
   ```

The release workflow rejects a tag that does not match the package version,
runs the complete local quality gate and Chromium benchmark, builds the wheel
and source distribution, builds the deterministic Agensi marketplace ZIP, and
checks the Python artifact metadata. It also invokes the checked-in composite
Action twice against a clean local fixture: the first run creates a baseline,
the second must pass a `quick` matrix, explicit smoke assertion, baseline delta
gate, and privacy-safe job summary. It then publishes the Python distributions
to PyPI through OIDC and publishes `server.json` to the MCP Registry through
GitHub OIDC. Only after both publications succeed does it create a GitHub
Release with the wheel, source archive, and Agensi ZIP attached. PyPI uploads
and Registry metadata publication are idempotent so a failed downstream job can
be retried safely.

The Agensi ZIP includes the local MCP configuration template and is pinned to
the package version. Its reproducible build can be checked locally:

```bash
python scripts/dev.py agensi-package
python scripts/dev.py agensi-package --check
sha256sum dist/agensi/web-delivery-qa-gate.zip
```

## Verify a release

The GitHub Actions `publish` job must succeed without `PYPI_API_TOKEN` or any
other repository secret. PyPI records the OIDC identity in the artifact
provenance:

```bash
curl -fsS \
  https://pypi.org/integrity/ego-webqa/0.8.2/ego_webqa-0.8.2-py3-none-any.whl/provenance |
  jq '.attestation_bundles[0].publisher'
```

Expected publisher fields are `kind: GitHub`,
`repository: ROY32172310/qa`, `workflow: release.yml`, and
`environment: pypi`.

The package itself can be verified from a clean `uvx` environment:

```bash
uvx --from ego-webqa==0.8.2 ego-webqa --version
```

Run the independent public-distribution verifier after a release:

```bash
python scripts/dev.py distribution-check --online
```

It writes `distribution-results/distribution.json` and
`distribution-results/summary.md`. The command hard-fails when the
version-specific PyPI record, the official MCP Registry record, or the GitHub
Release assets do not match `pyproject.toml`. PyPI's unpinned latest-version
record gets a 30-minute cache grace after upload; after that point a stale
latest version also fails. Glama version synchronization, Glama/TensorBlock
profile availability, and badge content types are observed as warnings because
those directories update asynchronously. Use
`--require-directories` only for an explicit strict audit:

```bash
python scripts/dev.py distribution-check --online --require-directories
```

The `distribution` GitHub Actions workflow runs this verifier after a
successful `release` workflow, every Monday, and on manual dispatch. It uploads
both evidence files even when verification fails. Directory reachability is
distribution evidence, not evidence of installs, retention, or
product-market fit.
