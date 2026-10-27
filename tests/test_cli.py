from __future__ import annotations

from ego_webqa.cli import _settings, build_parser
from ego_webqa.config import Viewport


def test_cli_viewport_and_selector_overrides() -> None:
    args = build_parser().parse_args(
        [
            "https://example.com",
            "--viewports",
            "390x844:phone,1280x800",
            "--ignore-selector",
            ".chat",
        ]
    )
    cfg = _settings(args)
    assert cfg.viewports == (Viewport(390, 844, "phone"), Viewport(1280, 800))
    assert cfg.ignore_selectors == (".chat",)
