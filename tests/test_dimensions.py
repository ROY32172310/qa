from __future__ import annotations

import ast
from pathlib import Path

from ego_webqa.dimensions import DIMENSIONS

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

    dynamic_navigation_codes = {"load_error", "ready_selector_not_found"}
    assert emitted | dynamic_navigation_codes == set(DIMENSIONS)


def test_registered_dimensions_have_complete_metadata() -> None:
    for code, dimension in DIMENSIONS.items():
        assert dimension.id == code
        assert dimension.version
        assert dimension.description
        assert dimension.detector
        assert dimension.default_severity in {"block", "warn", "info"}
        assert dimension.introduced_in
        assert dimension.profile in {"baseline", "accessibility"}
