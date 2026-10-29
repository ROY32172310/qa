# Releasing

Releases use PyPI Trusted Publishing. No PyPI token is stored in GitHub.

## One-time setup

1. In GitHub, create an environment named `pypi`.
2. In PyPI, add a pending trusted publisher for:
   - project: `ego-webqa`
   - owner: `ROY32172310`
   - repository: `qa`
   - workflow: `release.yml`
   - environment: `pypi`

## Publish a version

1. Set the same version in `pyproject.toml` and
   `src/ego_webqa/__init__.py`.
2. Update `CHANGELOG.md`.
3. Land the release commit on `master` and wait for CI to pass.
4. Create and push an annotated tag:

   ```bash
   git tag -a v0.4.0 -m "ego-webqa 0.4.0"
   git push github v0.4.0
   ```

The release workflow rejects a tag that does not match the package version,
runs the complete local quality gate and Chromium benchmark, builds the wheel
and source distribution, checks their metadata, and publishes them to PyPI
through OIDC.
