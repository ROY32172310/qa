from __future__ import annotations

import json
from pathlib import Path

import pytest

from ego_webqa.config import Settings, Viewport, load_settings


def test_viewport_parse_named_and_default() -> None:
    assert Viewport.parse("390x844:mobile") == Viewport(390, 844, "mobile")
    assert Viewport.parse("1280x800").name == "1280x800"


@pytest.mark.parametrize("value", ["", "390", "a x b", "100x300", "390x844:extra:name"])
def test_viewport_parse_rejects_invalid(value: str) -> None:
    with pytest.raises(ValueError):
        Viewport.parse(value)


def test_load_settings_json_and_unknown_key(tmp_path: Path) -> None:
    path = tmp_path / "webqa.json"
    path.write_text(
        json.dumps({"viewports": ["390x844:phone"], "min_font_px": 13}),
        encoding="utf-8",
    )
    cfg = load_settings(path)
    assert cfg.viewports == (Viewport(390, 844, "phone"),)
    assert cfg.min_font_px == 13

    path.write_text(json.dumps({"typo": 1}), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown config"):
        load_settings(path)


def test_invalid_threshold_is_rejected() -> None:
    with pytest.raises(ValueError, match="overlay_ratio"):
        Settings(overlay_ratio=1.2)
