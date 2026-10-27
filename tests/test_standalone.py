from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "ego_webqa"


def test_source_has_no_ego_private_imports() -> None:
    forbidden = ("ego_protocol", "ego_uri", "ego_test", "ego_devloop", "ego_ops")
    for path in SOURCE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            assert not any(name.startswith(forbidden) for name in names), (path, names)


def test_source_has_no_private_service_defaults() -> None:
    text = "\n".join(path.read_text(encoding="utf-8") for path in SOURCE.glob("*.py"))
    assert "egohub.tech" not in text
    assert "window.__EGO__" not in text
    assert ".ego-footer" not in text
