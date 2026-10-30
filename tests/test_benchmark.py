from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import pytest

from benchmarks import run as benchmark_run
from benchmarks.eval import (
    BenchmarkCase,
    BenchmarkConfigError,
    evaluate_cases,
    load_suite,
    render_markdown,
    select_cases,
)
from ego_webqa.dimensions import DIMENSIONS


def _case(
    case_id: str,
    expected: tuple[str, ...],
    *,
    clean: bool = False,
    severities: dict[str, Literal["error", "warning"]] | None = None,
) -> BenchmarkCase:
    return BenchmarkCase(
        id=case_id,
        fixture="fixture.html",
        target="",
        viewport="mobile",
        viewport_value="390x844:mobile",
        expected_issue_codes=expected,
        expected_clean=clean,
        expected_severities=severities or {},
        forbidden_issue_codes=(),
        profile="baseline",
        smoke=False,
        settings={},
        tags=("unit", "mobile"),
        rationale="unit test",
    )


def _obs(*issues: tuple[str, str], duration_ms: int = 100, error: str = "") -> dict[str, Any]:
    return {
        "issues": [
            {"code": code, "severity": severity, "viewport": "mobile"} for code, severity in issues
        ],
        "duration_ms": duration_ms,
        "error": error,
    }


def test_suite_expands_variants_and_covers_all_registered_dimensions() -> None:
    suite = load_suite(Path("benchmarks/suite.json"))
    assert len(suite.cases) >= 100
    assert len({case.id for case in suite.cases}) == len(suite.cases)
    assert {case.viewport for case in suite.cases} >= {"narrow", "mobile", "tablet", "desktop"}
    expected = {code for case in suite.cases for code in case.expected_issue_codes}
    assert expected == set(DIMENSIONS)


def test_suite_validation_rejects_missing_fixture(tmp_path: Path) -> None:
    data = {
        "schema_version": "1.0",
        "viewports": {"mobile": "390x844:mobile"},
        "cases": [
            {
                "id": "bad",
                "fixture": "missing.html",
                "expected_issue_codes": ["page_error"],
                "expected_clean": False,
                "rationale": "bad",
            }
        ],
    }
    path = tmp_path / "suite.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BenchmarkConfigError, match="fixture does not exist"):
        load_suite(path, tmp_path)


def test_selection_supports_ids_and_tags() -> None:
    cases = (_case("one", ("page_error",)), _case("two", (), clean=True))
    assert [case.id for case in select_cases(cases, ids=["two"])] == ["two"]
    assert [case.id for case in select_cases(cases, tags=["unit"])] == ["one", "two"]
    with pytest.raises(BenchmarkConfigError, match="unknown case"):
        select_cases(cases, ids=["missing"])


def test_metrics_distinguish_exact_matches_from_case_detection() -> None:
    cases = (
        _case("clean-tn", (), clean=True),
        _case("clean-fp", (), clean=True),
        _case("defect-tp", ("page_error",)),
        _case("defect-extra", ("page_error",)),
        _case("defect-fn", ("console_error",)),
        _case("warning-severity", ("tiny_fonts",), severities={"tiny_fonts": "warning"}),
    )
    result = evaluate_cases(
        cases,
        {
            "clean-tn": _obs(),
            "clean-fp": _obs(("page_error", "error")),
            "defect-tp": _obs(("page_error", "error")),
            "defect-extra": _obs(
                ("page_error", "error"),
                ("resource_failure", "error"),
            ),
            "defect-fn": _obs(),
            "warning-severity": _obs(("tiny_fonts", "error")),
        },
    )
    metrics = result["metrics"]
    assert metrics["exact_matches"] == 2
    assert metrics["case_level"]["tp"] == 3
    assert metrics["case_level"]["fp"] == 1
    assert metrics["case_level"]["fn"] == 1
    assert metrics["case_level"]["tn"] == 1
    assert metrics["dimension_metrics"]["page_error"]["fp"] == 1
    assert metrics["dimension_metrics"]["console_error"]["fn"] == 1
    assert result["failures"][0]["id"] == "clean-fp"
    assert any(item["id"] == "defect-extra" for item in result["failures"])
    assert any(item["id"] == "warning-severity" for item in result["failures"])


def test_markdown_report_is_honest_about_scope() -> None:
    suite_case = _case("clean", (), clean=True)
    result = evaluate_cases((suite_case,), {"clean": _obs(duration_ms=42)})
    markdown = render_markdown(
        result,
        {
            "generated_at": "2026-10-29T00:00:00+00:00",
            "tool_version": "0.3.0",
            "git_commit": "abc",
            "suite_sha256": "def",
            "browser": "chromium",
            "execution_profile": "controlled-local",
            "latency_role": "regression",
        },
    )
    assert "# ego-webqa benchmark" in markdown
    assert "not evidence of real-site coverage" in markdown
    assert "Execution profile: `controlled-local`" in markdown
    assert "Latency role: `regression`" in markdown
    assert "42" in markdown


def test_benchmark_environment_marks_serial_latency_as_regression_only() -> None:
    common = {
        "suite_sha256": "suite",
        "generated_at": "2026-10-30T00:00:00+00:00",
        "browser": "chromium",
        "wall_ms": 100,
    }

    serial = benchmark_run._environment(**common, jobs=1)
    parallel = benchmark_run._environment(**common, jobs=4)

    assert serial["execution_profile"] == "controlled-local"
    assert serial["latency_role"] == "regression"
    assert serial["latency_comparable"] is True
    assert parallel["latency_role"] == "throughput-only"
    assert parallel["latency_comparable"] is False
