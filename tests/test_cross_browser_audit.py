from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from ego_webqa.config import Settings, Viewport
from ego_webqa.engine import audit
from ego_webqa.server import LocalServer

pytestmark = [
    pytest.mark.cross_browser,
    pytest.mark.skipif(
        os.environ.get("EGO_WEBQA_CROSS_BROWSER") != "1",
        reason="set EGO_WEBQA_CROSS_BROWSER=1 after installing Firefox and WebKit",
    ),
    pytest.mark.skipif(
        not importlib.util.find_spec("playwright"), reason="playwright is not installed"
    ),
]


@pytest.fixture(scope="module")
def cross_browser_site(tmp_path_factory: pytest.TempPathFactory) -> LocalServer:
    root = tmp_path_factory.mktemp("cross-browser-site")
    (root / "clean.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport"
content="width=device-width"><title>Cross-browser clean</title><style>
body{margin:0;font:16px/1.5 system-ui;background:#fff;color:#111}
main{max-width:720px;padding:24px;margin:auto}button{min-height:48px;font-size:16px}
</style></head><body><main><h1>Ready in every engine</h1>
<p>This page remains inside a narrow mobile viewport.</p><button>Continue</button>
</main></body></html>""",
        encoding="utf-8",
    )
    (root / "overflow.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport"
content="width=device-width"><title>Cross-browser overflow</title><style>
body{margin:0;font:16px/1.5 system-ui;background:#fff;color:#111}
main{padding:24px}.wide{width:2400px;height:20px}
</style></head><body><main><h1>Overflow</h1>
<div class="wide">This content exceeds the viewport.</div>
</main></body></html>""",
        encoding="utf-8",
    )
    server = LocalServer(root)
    yield server
    server.close()


@pytest.mark.parametrize("engine", ["firefox", "webkit"])
def test_preview_engine_reports_clean_and_blocking_pages(
    engine: str,
    cross_browser_site: LocalServer,
    tmp_path: Path,
) -> None:
    settings = Settings(
        browser_engine=engine,
        viewports=(Viewport(390, 844, "mobile", mobile=True),),
        timeout_ms=15_000,
        settle_ms=100,
    )
    clean = audit(
        cross_browser_site.url("clean.html"),
        settings=settings,
        output_dir=tmp_path / engine / "clean",
        smoke=False,
    )
    assert clean.status == "pass"
    assert clean.runtime["browser_engine"] == engine
    assert (tmp_path / engine / "clean" / "screenshots" / "mobile.png").is_file()

    broken = audit(
        cross_browser_site.url("overflow.html"),
        settings=settings,
        output_dir=tmp_path / engine / "broken",
        smoke=False,
    )
    assert broken.runtime["browser_channel"] == f"bundled-{engine}"
    assert "horizontal_overflow" in {issue.code for issue in broken.issues}
