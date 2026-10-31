from __future__ import annotations

import json
from pathlib import Path

from scripts import verify_distribution

VERSION = "1.2.3"


class FakeFetcher(verify_distribution.Fetcher):
    def __init__(self, responses: dict[str, verify_distribution.HttpResponse]) -> None:
        self.responses = responses

    def __call__(self, url: str) -> verify_distribution.HttpResponse:
        try:
            return self.responses[url]
        except KeyError as exc:
            raise verify_distribution.DistributionError(f"unexpected URL: {url}") from exc


def _json_response(url: str, payload: dict[str, object]) -> verify_distribution.HttpResponse:
    return verify_distribution.HttpResponse(
        status=200,
        content_type="application/json",
        body=json.dumps(payload).encode(),
        url=url,
    )


def _text_response(url: str, body: str) -> verify_distribution.HttpResponse:
    return verify_distribution.HttpResponse(
        status=200,
        content_type="text/html; charset=utf-8",
        body=body.encode(),
        url=url,
    )


def _image_response(url: str, content_type: str = "image/png") -> verify_distribution.HttpResponse:
    return verify_distribution.HttpResponse(
        status=200,
        content_type=content_type,
        body=b"image",
        url=url,
    )


def _responses() -> dict[str, verify_distribution.HttpResponse]:
    pypi_version_url = "https://pypi.org/pypi/ego-webqa/1.2.3/json"
    pypi_latest_url = "https://pypi.org/pypi/ego-webqa/json"
    registry_url = (
        "https://registry.modelcontextprotocol.io/v0.1/servers" "?search=io.github.ROY32172310%2Fqa"
    )
    release_url = "https://api.github.com/repos/ROY32172310/qa/releases/tags/v1.2.3"
    return {
        pypi_version_url: _json_response(
            pypi_version_url,
            {
                "info": {"version": VERSION},
                "urls": [
                    {
                        "filename": f"ego_webqa-{VERSION}-py3-none-any.whl",
                        "upload_time_iso_8601": "2026-10-30T23:50:00Z",
                    },
                    {
                        "filename": f"ego_webqa-{VERSION}.tar.gz",
                        "upload_time_iso_8601": "2026-10-30T23:50:00Z",
                    },
                ],
            },
        ),
        pypi_latest_url: _json_response(
            pypi_latest_url,
            {
                "info": {"version": VERSION},
                "urls": [],
            },
        ),
        registry_url: _json_response(
            registry_url,
            {
                "servers": [
                    {
                        "server": {
                            "name": verify_distribution.MCP_SERVER_NAME,
                            "version": VERSION,
                        }
                    }
                ]
            },
        ),
        release_url: _json_response(
            release_url,
            {
                "tag_name": f"v{VERSION}",
                "draft": False,
                "prerelease": False,
                "assets": [
                    {"name": f"ego_webqa-{VERSION}-py3-none-any.whl"},
                    {"name": f"ego_webqa-{VERSION}.tar.gz"},
                    {"name": "web-delivery-qa-gate.zip"},
                ],
            },
        ),
        verify_distribution.GLAMA_PROFILE: _text_response(
            verify_distribution.GLAMA_PROFILE,
            f"uvx --from ego-webqa=={VERSION} ego-webqa setup",
        ),
        verify_distribution.GLAMA_BADGE: _image_response(
            verify_distribution.GLAMA_BADGE,
            "image/png",
        ),
        verify_distribution.TENSORBLOCK_PROFILE: _text_response(
            verify_distribution.TENSORBLOCK_PROFILE,
            "<html>profile</html>",
        ),
        verify_distribution.TENSORBLOCK_BADGE: _image_response(
            verify_distribution.TENSORBLOCK_BADGE,
            "image/svg+xml; charset=utf-8",
        ),
    }


def _report(
    responses: dict[str, verify_distribution.HttpResponse] | None = None,
    *,
    require_directories: bool = False,
) -> verify_distribution.VerificationReport:
    return verify_distribution.verify_distribution(
        FakeFetcher(responses or _responses()),
        expected_version=VERSION,
        require_directories=require_directories,
        checked_at="2026-10-31T00:00:00Z",
    )


def _check(
    report: verify_distribution.VerificationReport,
    system: str,
) -> verify_distribution.CheckResult:
    return next(check for check in report.checks if check.system == system)


def test_distribution_verifier_accepts_all_public_systems() -> None:
    report = _report()

    assert report.status == "pass"
    assert all(check.status == "pass" for check in report.checks)
    assert report.as_dict()["summary"] == {"passed": 7, "warnings": 0, "failed": 0}


def test_pypi_latest_mismatch_is_blocking() -> None:
    responses = _responses()
    pypi_version_url = "https://pypi.org/pypi/ego-webqa/1.2.3/json"
    responses[pypi_version_url] = _json_response(
        pypi_version_url,
        {
            "info": {"version": "1.2.2"},
            "urls": [],
        },
    )

    report = _report(responses)

    assert report.status == "fail"
    assert _check(report, "pypi").status == "fail"
    assert "version endpoint returned 1.2.2" in _check(report, "pypi").detail


def test_pypi_latest_cache_lag_inside_grace_is_warning() -> None:
    responses = _responses()
    pypi_latest_url = "https://pypi.org/pypi/ego-webqa/json"
    responses[pypi_latest_url] = _json_response(
        pypi_latest_url,
        {
            "info": {"version": "1.2.2"},
            "urls": [],
        },
    )

    report = _report(responses)

    assert report.status == "warn"
    assert _check(report, "pypi").status == "warn"
    assert "cache grace" in _check(report, "pypi").detail


def test_pypi_latest_cache_lag_after_grace_is_blocking() -> None:
    responses = _responses()
    pypi_latest_url = "https://pypi.org/pypi/ego-webqa/json"
    responses[pypi_latest_url] = _json_response(
        pypi_latest_url,
        {
            "info": {"version": "1.2.2"},
            "urls": [],
        },
    )

    report = verify_distribution.verify_distribution(
        FakeFetcher(responses),
        expected_version=VERSION,
        checked_at="2026-10-31T03:00:00Z",
    )

    assert report.status == "fail"
    assert _check(report, "pypi").status == "fail"
    assert "PyPI latest is 1.2.2" in _check(report, "pypi").detail


def test_registry_missing_expected_version_is_blocking() -> None:
    responses = _responses()
    registry_url = (
        "https://registry.modelcontextprotocol.io/v0.1/servers" "?search=io.github.ROY32172310%2Fqa"
    )
    responses[registry_url] = _json_response(
        registry_url,
        {
            "servers": [
                {
                    "server": {
                        "name": verify_distribution.MCP_SERVER_NAME,
                        "version": "1.2.2",
                    }
                }
            ]
        },
    )

    report = _report(responses)

    assert report.status == "fail"
    assert _check(report, "official-mcp-registry").status == "fail"
    assert "observed: 1.2.2" in _check(report, "official-mcp-registry").detail


def test_release_missing_agensi_asset_is_blocking() -> None:
    responses = _responses()
    release_url = "https://api.github.com/repos/ROY32172310/qa/releases/tags/v1.2.3"
    responses[release_url] = _json_response(
        release_url,
        {
            "tag_name": "v1.2.3",
            "draft": False,
            "prerelease": False,
            "assets": [
                {"name": "ego_webqa-1.2.3-py3-none-any.whl"},
                {"name": "ego_webqa-1.2.3.tar.gz"},
            ],
        },
    )

    report = _report(responses)

    assert report.status == "fail"
    assert _check(report, "github-release").status == "fail"
    assert "Agensi ZIP" in _check(report, "github-release").detail


def test_directory_version_lag_warns_without_blocking_by_default(tmp_path: Path) -> None:
    responses = _responses()
    responses[verify_distribution.GLAMA_PROFILE] = _text_response(
        verify_distribution.GLAMA_PROFILE,
        "uvx --from ego-webqa==1.2.2 ego-webqa setup",
    )

    report = _report(responses)

    assert report.status == "warn"
    assert _check(report, "glama-profile").status == "warn"
    assert (
        verify_distribution.main(
            ["--online", "--version", VERSION, "--out", str(tmp_path)],
            fetcher=FakeFetcher(responses),
        )
        == 0
    )


def test_require_directories_promotes_version_lag_to_failure() -> None:
    responses = _responses()
    responses[verify_distribution.GLAMA_PROFILE] = _text_response(
        verify_distribution.GLAMA_PROFILE,
        "uvx --from ego-webqa==1.2.2 ego-webqa setup",
    )

    report = _report(responses, require_directories=True)

    assert report.status == "fail"
    assert _check(report, "glama-profile").required is True
    assert _check(report, "glama-profile").status == "fail"


def test_bad_badge_content_type_is_actionable() -> None:
    responses = _responses()
    responses[verify_distribution.GLAMA_BADGE] = verify_distribution.HttpResponse(
        status=200,
        content_type="text/html",
        body=b"not an image",
        url=verify_distribution.GLAMA_BADGE,
    )

    report = _report(responses)

    assert report.status == "warn"
    assert _check(report, "glama-badge").status == "warn"
    assert "non-image" in _check(report, "glama-badge").detail


def test_malformed_json_is_reported_as_blocking_and_actionable() -> None:
    responses = _responses()
    pypi_version_url = "https://pypi.org/pypi/ego-webqa/1.2.3/json"
    responses[pypi_version_url] = verify_distribution.HttpResponse(
        status=200,
        content_type="application/json",
        body=b"{",
        url=pypi_version_url,
    )

    report = _report(responses)

    assert report.status == "fail"
    assert _check(report, "pypi").status == "fail"
    assert "malformed JSON" in _check(report, "pypi").detail


def test_writer_produces_stable_json_and_markdown_evidence(tmp_path: Path) -> None:
    report = _report()

    verify_distribution.write_evidence(report, tmp_path)
    first_json = (tmp_path / "distribution.json").read_bytes()
    first_markdown = (tmp_path / "summary.md").read_bytes()
    verify_distribution.write_evidence(report, tmp_path)

    assert (tmp_path / "distribution.json").read_bytes() == first_json
    assert (tmp_path / "summary.md").read_bytes() == first_markdown
    payload = json.loads(first_json)
    assert payload["checked_at"] == "2026-10-31T00:00:00Z"
    assert payload["status"] == "pass"
    assert b"do not prove adoption" in first_markdown
