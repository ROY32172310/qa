from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from ego_webqa.config import Settings, Viewport
from ego_webqa.engine import audit
from ego_webqa.server import LocalServer

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        not importlib.util.find_spec("playwright"), reason="playwright is not installed"
    ),
]


@pytest.fixture(scope="module")
def served(tmp_path_factory: pytest.TempPathFactory) -> LocalServer:
    root = tmp_path_factory.mktemp("site")
    (root / "clean.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width">
<title>Clean page</title><style>
body{margin:0;font:16px/1.5 system-ui;background:#fff;color:#111}
main{max-width:720px;padding:32px;margin:auto}h1{font-size:32px}
button{height:48px;min-width:140px;font-size:16px}img{width:120px;height:120px}
</style></head><body><main><h1>Ready to ship</h1><p>This page has readable content.</p>
<button id="start"
onclick="document.querySelector('#result').textContent='Started'">Start now</button>
<p id="result"></p>
<img src="/pixel.svg" width="120" height="120" alt="sample"></main></body></html>""",
        encoding="utf-8",
    )
    (root / "pixel.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120">'
        '<rect width="120" height="120" fill="#ddd"/></svg>',
        encoding="utf-8",
    )
    (root / "broken.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width">
<title>Broken page</title><style>body{margin:0;font-size:16px}.wide{width:2400px;height:20px}
button{height:20px;width:20px}.small{font-size:8px}</style></head><body>
<div class="wide">overflow</div><span class="small">tiny text</span>
<img src="/missing.png" width="100" height="100" alt="missing">
<button onclick="void 0">Buy</button><script>console.error("bad production log")</script>
</body></html>""",
        encoding="utf-8",
    )
    server = LocalServer(root)
    yield server
    server.close()


def test_clean_page_passes(served: LocalServer, tmp_path: Path) -> None:
    report = audit(
        served.url("clean.html"),
        settings=Settings(viewports=(Viewport(390, 844, "mobile"),), settle_ms=50),
        output_dir=tmp_path,
    )
    assert report.status == "pass", report.to_dict()["issues"]
    assert report.smoke["found"] is True
    assert report.smoke["changed"] is True
    assert Path(report.screenshots[0]).is_file()


def test_broken_page_finds_real_defects(served: LocalServer, tmp_path: Path) -> None:
    report = audit(
        served.url("broken.html"),
        settings=Settings(viewports=(Viewport(390, 844, "mobile"),), settle_ms=50),
        output_dir=tmp_path,
    )
    codes = {issue.code for issue in report.issues}
    assert report.status == "fail"
    assert {"horizontal_overflow", "console_error", "unreadable_font", "broken_image"} <= codes
