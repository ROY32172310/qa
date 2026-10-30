from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from ego_webqa.config import Settings, SmokeStep, Viewport
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
    (root / "flow.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport"
content="width=device-width"><title>Cross-browser text flow</title><style>
body{margin:0;font:16px/1.5 system-ui;background:#fff;color:#111}
main{max-width:720px;padding:24px;margin:auto}button{min-height:48px;font-size:16px}
</style></head><body><main><h1>Counter</h1>
<button id="increment" onclick="
const count=document.querySelector('#count');
count.textContent=String(Number(count.textContent)+1)
">Increment</button><output id="count">0</output>
</main></body></html>""",
        encoding="utf-8",
    )
    (root / "clipped.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport"
content="width=device-width"><title>Cross-browser clipped text</title><style>
body{margin:0;font:16px/1.5 system-ui;background:#fff;color:#111}
main{padding:24px}.hard{width:150px;overflow:hidden;white-space:nowrap}
</style></head><body><main><h1>Clipped text</h1>
<p id="hard" class="hard">Premium account renewal is overdue</p>
</main></body></html>""",
        encoding="utf-8",
    )
    (root / "clipping-control.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport"
content="width=device-width"><title>Cross-browser clipping controls</title><style>
body{margin:0;font:16px/1.5 system-ui;background:#fff;color:#111}
main{padding:24px}.bounded{width:150px;white-space:nowrap}
.ellipsis{overflow:hidden;text-overflow:ellipsis}.scroll{overflow-x:auto}
</style></head><body><main><h1>Clipping controls</h1>
<p id="ellipsis" class="bounded ellipsis">Premium account renewal is overdue</p>
<div id="scroll" class="bounded scroll">Scrollable account activity details</div>
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


@pytest.mark.parametrize("engine", ["firefox", "webkit"])
def test_preview_engine_verifies_a_bounded_text_flow(
    engine: str,
    cross_browser_site: LocalServer,
    tmp_path: Path,
) -> None:
    report = audit(
        cross_browser_site.url("flow.html"),
        settings=Settings(
            browser_engine=engine,
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            timeout_ms=15_000,
            settle_ms=100,
            smoke_settle_ms=10,
            smoke_flow=(
                SmokeStep("click", selector="#increment"),
                SmokeStep("expect_text", selector="#count", pattern=r"^1$"),
            ),
        ),
        output_dir=tmp_path / engine / "flow",
    )
    assert report.status == "pass"
    assert report.smoke["success"] is True
    assert report.smoke["steps"][1]["text_source"] == "text"
    assert report.runtime["browser_engine"] == engine


@pytest.mark.parametrize("engine", ["firefox", "webkit"])
def test_preview_engine_detects_only_hidden_text_without_an_escape_affordance(
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
    broken = audit(
        cross_browser_site.url("clipped.html"),
        settings=settings,
        output_dir=tmp_path / engine / "clipped",
        smoke=False,
    )
    clipped = next(issue for issue in broken.issues if issue.code == "clipped_text")
    assert clipped.evidence["samples"][0]["selector"] == "#hard"

    control = audit(
        cross_browser_site.url("clipping-control.html"),
        settings=settings,
        output_dir=tmp_path / engine / "clipping-control",
        smoke=False,
    )
    assert "clipped_text" not in {issue.code for issue in control.issues}
