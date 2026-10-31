from __future__ import annotations

import ast
from pathlib import Path

from ego_webqa.dimensions import (
    DIMENSIONS,
    PROFILE_NAMES,
    profile_includes_dimension,
)

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "src" / "ego_webqa" / "engine.py"


def test_engine_issue_codes_are_exactly_the_closed_registry() -> None:
    tree = ast.parse(ENGINE.read_text(encoding="utf-8"))
    emitted: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "Issue":
            continue
        if node.args and isinstance(node.args[0], ast.Constant):
            value = node.args[0].value
            if isinstance(value, str):
                emitted.add(value)
        for keyword in node.keywords:
            if keyword.arg != "code" or not isinstance(keyword.value, ast.Constant):
                continue
            value = keyword.value.value
            if isinstance(value, str):
                emitted.add(value)

    dynamic_codes = {
        "load_error",
        "ready_selector_not_found",
        "horizontal_overflow",
        "text_scale_layout_break",
        "smoke_flow_text_assertion_failed",
    }
    assert emitted | dynamic_codes == set(DIMENSIONS)


def test_registered_dimensions_have_complete_metadata() -> None:
    for code, dimension in DIMENSIONS.items():
        assert dimension.id == code
        assert dimension.version
        assert dimension.description
        assert dimension.detector
        assert dimension.default_severity in {"block", "warn", "info"}
        assert dimension.introduced_in
        assert dimension.profile in {"baseline", "performance", "accessibility"}


def test_profiles_are_closed_and_additive() -> None:
    assert PROFILE_NAMES == ("baseline", "performance", "accessibility", "full")
    assert profile_includes_dimension("baseline", "horizontal_overflow")
    assert not profile_includes_dimension("baseline", "slow_load_event")
    assert profile_includes_dimension("performance", "slow_load_event")
    assert not profile_includes_dimension("performance", "missing_html_lang")
    assert profile_includes_dimension("accessibility", "missing_html_lang")
    assert not profile_includes_dimension("accessibility", "slow_load_event")
    assert profile_includes_dimension("full", "slow_load_event")
    assert profile_includes_dimension("full", "missing_html_lang")
