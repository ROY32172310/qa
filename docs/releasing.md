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
   git tag -a v0.6.0 -m "ego-webqa 0.6.0"
   git push github v0.6.0
   ```

The release workflow rejects a tag that does not match the package version,
runs the complete local quality gate and Chromium benchmark, builds the wheel
and source distribution, checks their metadata, publishes them to PyPI through
OIDC, publishes `server.json` to the MCP Registry through GitHub OIDC, and
creates a GitHub Release with the same artifacts attached. PyPI uploads and
Registry metadata publication are idempotent so a failed downstream job can be
retried safely.

## Verify a release

The GitHub Actions `publish` job must succeed without `PYPI_API_TOKEN` or any
other repository secret. PyPI records the OIDC identity in the artifact
provenance:

```bash
curl -fsS \
  https://pypi.org/integrity/ego-webqa/0.6.0/ego_webqa-0.6.0-py3-none-any.whl/provenance |
  jq '.attestation_bundles[0].publisher'
```

Expected publisher fields are `kind: GitHub`,
`repository: ROY32172310/qa`, `workflow: release.yml`, and
`environment: pypi`.

The package itself can be verified from a clean `uvx` environment:

```bash
uvx --from ego-webqa==0.6.0 ego-webqa --version
```
