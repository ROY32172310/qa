from __future__ import annotations

import base64
import contextlib
import http.server
import importlib.util
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from ego_webqa.config import DimensionOverride, Settings, SmokeStep, Viewport
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
onclick="document.querySelector('#result').textContent='Started';history.pushState({},'','#started')">
Start now</button>
<p id="result"></p>
<a href="#home"><img src="/pixel.svg" width="120" height="120" alt="Sample home"></a>
</main></body></html>""",
        encoding="utf-8",
    )
    (root / "pixel.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120">'
        '<rect width="120" height="120" fill="#ddd"/></svg>',
        encoding="utf-8",
    )
    (root / "ratio.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="19">'
        '<rect width="24" height="19" fill="#ddd"/></svg>',
        encoding="utf-8",
    )
    (root / "overlay.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport"
content="width=device-width"><title>Overlay calibration</title><style>
body{margin:0;font:16px/1.5 system-ui;background:#fff;color:#111}main{padding:32px}
.overlay{position:fixed;top:0;width:250px;height:100vh}
.offscreen{left:-250px}.visible{left:10vw;width:80vw;height:80vh}
</style></head><body><main><h1>Overlay calibration</h1>
<p>Only overlays intersecting the viewport are delivery risks.</p></main>
<div id="offscreen" class="overlay offscreen"></div>
<div id="modal" class="overlay visible"></div></body></html>""",
        encoding="utf-8",
    )
    (root / "media.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport"
content="width=device-width"><title>Media calibration</title><style>
body{margin:0;font:16px/1.5 system-ui;background:#fff;color:#111}main{padding:32px}
</style></head><body><main><h1>Media calibration</h1>
<p>Small icon rounding is not a delivery-blocking distortion.</p>
<img id="tiny" src="/ratio.svg" width="8" height="7" alt="Small rounded icon">
<img id="distorted" src="/pixel.svg" width="100" height="200" alt="Distorted hero">
<img id="correct" src="/pixel.svg" width="120" height="120" alt="Correct image">
</main></body></html>""",
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
    (root / "missing-favicon.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width">
<link rel="icon" href="/favicon.ico"><title>Missing favicon</title><style>
body{margin:0;font:16px/1.5 system-ui}main{padding:32px}</style></head>
<body><main><h1>Favicons are not delivery blockers</h1>
<p>A missing icon must not fail an otherwise usable page.</p></main></body></html>""",
        encoding="utf-8",
    )
    (root / "side-effect.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width">
<title>Side effect</title><style>
body{margin:0;font:16px/1.5 system-ui;background:#fff;color:#111}
main{max-width:720px;padding:32px;margin:auto}button{height:48px;min-width:140px;font-size:16px}
</style></head><body><main><h1>Safe checkout</h1>
<p>This action attempts a state-changing network request.</p>
<button id="buy" onclick="fetch('/mutate',{method:'POST'}).catch(()=>{})">Buy now</button>
</main></body></html>""",
        encoding="utf-8",
    )
    (root / "late.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width">
<title>Late page</title><style>body{margin:0;font:16px/1.5 system-ui}main{padding:32px}</style>
</head><body><p>Loading</p><script>
setTimeout(() => {
  const main = document.createElement("main");
  main.id = "ready";
  main.innerHTML = "<h1>Rendered</h1><p>Delayed content is now ready.</p>";
  document.body.append(main);
}, 120);
</script></body></html>""",
        encoding="utf-8",
    )
    (root / "flow.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width">
<title>Bounded flow</title><style>
body{margin:0;font:16px/1.5 system-ui;background:#fff;color:#111}
main{max-width:720px;padding:32px;margin:auto}
input,button{min-height:48px;font-size:16px}
[hidden]{display:none!important}
</style></head><body><main><h1>Create a preview</h1>
<input id="email" aria-label="Email"><button id="continue" onclick="
const success=document.querySelector('#success');
const error=document.querySelector('#error');
if(document.querySelector('#email').value){
  success.hidden=false;error.hidden=true;history.pushState({},'','#complete');
}else{success.hidden=true;error.hidden=false}
">Continue</button>
<p id="error" hidden>Email is required.</p>
<p id="success" hidden>Preview created.</p>
</main></body></html>""",
        encoding="utf-8",
    )
    (root / "flow-error.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width">
<title>Flow error</title><style>
body{margin:0;font:16px/1.5 system-ui;background:#fff;color:#111}main{padding:32px}
button{min-height:48px;font-size:16px}
</style></head><body><main><h1>Flow exception</h1>
<button id="boom" onclick="setTimeout(() => { throw new Error('flow boom') }, 0)">
Continue</button><p id="done">Visible result</p></main></body></html>""",
        encoding="utf-8",
    )
    (root / "navigate.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width">
<title>Navigate CTA</title><style>
body{margin:0;font:16px/1.5 system-ui;background:#fff;color:#111}
main{max-width:720px;padding:32px;margin:auto}a{display:inline-flex;align-items:center;
min-height:48px;font-size:16px}</style></head><body><main><h1>Navigate page</h1>
<p>The CTA opens a new document.</p><a id="continue" href="/after.html">Continue</a>
</main></body></html>""",
        encoding="utf-8",
    )
    (root / "after.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width">
<title>Complete</title><style>body{margin:0;font:16px/1.5 system-ui}main{padding:32px}</style>
</head><body><main id="done"><h1>Complete</h1><p>The CTA reached the destination.</p>
</main></body></html>""",
        encoding="utf-8",
    )
    (root / "inaccessible.html").write_text(
        """<!doctype html><html><head><meta name="viewport" content="width=device-width">
<title>Accessibility problems</title><style>
body{margin:0;font:16px/1.5 system-ui;background:#fff;color:#111}
main{max-width:720px;padding:32px;margin:auto}button{min-width:48px;min-height:48px;font-size:16px}
</style></head><body><main><h1>Accessibility fixture</h1><h3>Skipped level</h3>
<p>This page intentionally contains multiple accessibility defects.</p>
<img src="/pixel.svg" width="80" height="80">
<button id="icon-only"><svg width="24" height="24" aria-hidden="true"><path d="M0 0h24v24H0z">
</path></svg></button>
<button tabindex="2" aria-label="Positive tab order">Tab order</button>
<div id="duplicate">first</div><div id="duplicate">second</div>
<div aria-hidden="true"><button>Hidden focus target</button></div>
</main></body></html>""",
        encoding="utf-8",
    )
    (root / "a11y-labeled.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width">
<title>Labeled form</title><style>
body{margin:0;font:16px/1.5 system-ui;background:#fff;color:#111}main{padding:32px}
input,button{min-height:48px;font-size:16px}
</style></head><body><main><h1>Labeled form</h1>
<p>Standard explicit labels must remain auditable.</p>
<form><label for="email">Email</label><input id="email" type="email">
<button type="submit">Continue</button></form>
</main></body></html>""",
        encoding="utf-8",
    )
    (root / "text-scale-clean.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width">
<title>Text scale control</title><style>
body{margin:0;font:16px/1.5 system-ui;background:#fff;color:#111}main{padding:24px}
.actions{display:flex;flex-wrap:wrap;gap:12px}button{min-height:48px;font-size:16px}
</style></head><body><main><h1>Flexible enlarged text</h1>
<p>This paragraph wraps inside the viewport when text is enlarged.</p>
<div class="actions"><button>Review account</button><button>Contact support</button></div>
</main></body></html>""",
        encoding="utf-8",
    )
    (root / "text-scale-break.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width">
<title>Text scale break</title><style>
body{margin:0;font:16px/1.5 system-ui;background:#fff;color:#111}main{padding:24px}
.headline{font-size:30px;white-space:nowrap}button{min-height:48px;font-size:16px}
</style></head><body><main><h1 class="headline">Quarterly account activity and status</h1>
<p>Enlarged text must remain inside the viewport.</p><button>Continue</button>
</main></body></html>""",
        encoding="utf-8",
    )
    (root / "safe-area-clean.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport"
content="width=device-width,viewport-fit=cover"><title>Safe area control</title><style>
body{margin:0;font:16px/1.5 system-ui;background:#fff;color:#111}main{padding:24px 24px 110px}
.bottom{position:fixed;left:16px;right:16px;bottom:0;min-height:56px;
padding:4px 12px env(safe-area-inset-bottom,0px);background:#17202a}
button{width:100%;min-height:48px;font-size:16px}
</style></head><body><main><h1>Preferences</h1><p>Content stays above the action bar.</p>
</main><div class="bottom"><button>Save preferences</button></div></body></html>""",
        encoding="utf-8",
    )
    (root / "safe-area-break.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width">
<title>Safe area break</title><style>
body{margin:0;font:16px/1.5 system-ui;background:#fff;color:#111}main{padding:24px 24px 110px}
.bottom{position:fixed;left:16px;right:16px;bottom:0;min-height:56px;
padding:4px 12px;background:#17202a}button{width:100%;min-height:48px;font-size:16px}
</style></head><body><main><h1>Preferences</h1><p>Content stays above the action bar.</p>
</main><div class="bottom"><button>Save preferences</button></div></body></html>""",
        encoding="utf-8",
    )
    (root / "shadow.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width">
<title>Shadow page</title><style>
body{margin:0;font:16px/1.5 system-ui;background:#fff;color:#111}main{padding:32px}
</style></head><body><main><h1>Shadow component</h1><p>Composed tree fixture.</p></main>
<shadow-demo></shadow-demo><script>
const host = document.querySelector("shadow-demo");
const root = host.attachShadow({mode: "open"});
root.innerHTML = `<button id="shadow-cta" style="width:20px;height:20px;font-size:16px"
onclick="this.getRootNode().querySelector('#shadow-result').textContent='Started'">
Start now</button>
<span id="shadow-result"></span>
<span id="shadow-small" style="font-size:8px">shadow tiny text</span>
<img id="shadow-image" src="/missing-shadow.png" width="40" height="40">
<button id="shadow-unnamed" style="width:48px;height:48px"></button>`;
</script></body></html>""",
        encoding="utf-8",
    )
    (root / "network-active.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width">
<title>Active network</title><style>body{margin:0;font:16px/1.5 system-ui}main{padding:32px}
</style></head><body><main><h1>Continuously active page</h1>
<p>This fixture deliberately never reaches network idle.</p></main><script>
setInterval(() => fetch("/pixel.svg?t=" + Date.now()).catch(() => {}), 80);
</script></body></html>""",
        encoding="utf-8",
    )
    server = LocalServer(root)
    yield server
    server.close()


def test_clean_page_passes(served: LocalServer, tmp_path: Path) -> None:
    report = audit(
        served.url("clean.html"),
        settings=Settings(
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            settle_ms=50,
            smoke_success_selector="#result",
            smoke_success_url_pattern=r"#started$",
        ),
        output_dir=tmp_path,
    )
    assert report.status == "pass", report.to_dict()["issues"]
    assert report.smoke["found"] is True
    assert report.smoke["changed"] is True
    assert report.smoke["success"] is True
    assert all(assertion["matched"] for assertion in report.smoke["assertions"])
    assert (tmp_path / report.screenshots[0]).is_file()
    environment = report.viewports[0]["measurements"]["environment"]
    assert report.viewports[0]["measurements"]["viewport"]["width"] == 390
    assert "Mobile" in environment["userAgent"]
    assert environment["maxTouchPoints"] > 0
    assert environment["coarsePointer"] is True


def test_accessibility_labels_do_not_crash_with_closed_detectors(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    report = audit(
        served.url("a11y-labeled.html"),
        settings=Settings(
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            profile="accessibility",
            settle_ms=0,
        ),
        output_dir=tmp_path,
        smoke=False,
    )
    assert report.status == "pass", report.to_dict()["issues"]


def test_governed_threshold_override_changes_detection(
    tmp_path: Path,
) -> None:
    root = tmp_path / "soft-font-site"
    root.mkdir()
    (root / "index.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport"
content="width=device-width"><title>Font threshold</title><style>
body{margin:0;font:16px/1.5 system-ui}main{padding:32px}
.detail{font-size:11px}
</style></head><body><main><h1>Readable heading</h1>
<p>Readable body copy remains unchanged.</p>
<ul class="detail"><li>One</li><li>Two</li><li>Three</li><li>Four</li><li>Five</li></ul>
</main></body></html>""",
        encoding="utf-8",
    )
    viewport = Viewport(390, 844, "mobile", mobile=True)
    with LocalServer(root) as server:
        baseline = audit(
            server.url(),
            settings=Settings(viewports=(viewport,), settle_ms=0),
            output_dir=tmp_path / "baseline",
            smoke=False,
        )
        governed = audit(
            server.url(),
            settings=Settings(
                viewports=(viewport,),
                settle_ms=0,
                overrides=(
                    DimensionOverride(
                        dimension_id="tiny_fonts",
                        reason="Documented compact annotation scale",
                        owner="design-system",
                        expires="2999-12-31",
                        parameters={"min_font_px": 11},
                    ),
                ),
            ),
            output_dir=tmp_path / "governed",
            smoke=False,
        )

    assert "tiny_fonts" in {issue.code for issue in baseline.issues}
    assert "tiny_fonts" not in {issue.code for issue in governed.issues}
    assert governed.settings["min_font_px"] == 11


def test_default_viewports_keep_stable_order_during_parallel_execution(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    report = audit(
        served.url("clean.html"),
        settings=Settings(settle_ms=0),
        output_dir=tmp_path,
        smoke=False,
    )
    assert [row["viewport"]["name"] for row in report.viewports] == [
        "mobile-360-100-safe0",
        "mobile-360-100-safe34",
        "mobile-360-150-safe0",
        "mobile-360-150-safe34",
        "mobile-390-100-safe0",
        "mobile-390-100-safe34",
        "mobile-390-150-safe0",
        "mobile-390-150-safe34",
    ]
    assert report.screenshots == [
        "screenshots/mobile-360-100-safe0.png",
        "screenshots/mobile-360-100-safe34.png",
        "screenshots/mobile-360-150-safe0.png",
        "screenshots/mobile-360-150-safe34.png",
        "screenshots/mobile-390-100-safe0.png",
        "screenshots/mobile-390-100-safe34.png",
        "screenshots/mobile-390-150-safe0.png",
        "screenshots/mobile-390-150-safe34.png",
    ]
    assert all((tmp_path / screenshot).is_file() for screenshot in report.screenshots)


def test_missing_favicon_does_not_create_console_error(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    report = audit(
        served.url("missing-favicon.html"),
        settings=Settings(
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            settle_ms=50,
        ),
        output_dir=tmp_path,
        smoke=False,
    )
    assert report.status == "pass", report.to_dict()["issues"]
    assert report.viewports[0]["console_errors"] == []


def test_broken_page_finds_real_defects(served: LocalServer, tmp_path: Path) -> None:
    report = audit(
        served.url("broken.html"),
        settings=Settings(
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            settle_ms=50,
        ),
        output_dir=tmp_path,
    )
    codes = {issue.code for issue in report.issues}
    assert report.status == "fail"
    assert {
        "horizontal_overflow",
        "console_error",
        "unreadable_font",
        "broken_image",
        "resource_failure",
    } <= codes
    network_issue = next(issue for issue in report.issues if issue.code == "resource_failure")
    details = network_issue.evidence["failure_details"]
    assert details[0]["kind"] == "http_error"
    assert details[0]["resource_type"] == "image"
    assert details[0]["frame_url"] == served.url("broken.html")
    assert details[0]["same_origin"] is True
    assert details[0]["status"] == 404


def test_offscreen_fixed_overlay_is_not_a_huge_overlay(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    report = audit(
        served.url("overlay.html"),
        settings=Settings(
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            settle_ms=0,
        ),
        output_dir=tmp_path,
        smoke=False,
    )
    overlays = [issue for issue in report.issues if issue.code == "huge_overlay"]
    assert len(overlays) == 1
    assert overlays[0].evidence["selector"] == "#modal"
    assert overlays[0].evidence["coverage"] >= 0.64


def test_tiny_media_rounding_is_not_reported_as_distortion(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    report = audit(
        served.url("media.html"),
        settings=Settings(
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            settle_ms=0,
        ),
        output_dir=tmp_path,
        smoke=False,
    )
    distortion = next(issue for issue in report.issues if issue.code == "media_distortion")
    selectors = {item["selector"] for item in distortion.evidence["media"]}
    assert "#distorted" in selectors
    assert "#tiny" not in selectors
    assert "#correct" not in selectors


def test_safe_smoke_blocks_state_changing_requests(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    report = audit(
        served.url("side-effect.html"),
        settings=Settings(
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            settle_ms=50,
            smoke_mode="safe",
        ),
        output_dir=tmp_path,
    )
    assert report.smoke["mode"] == "safe"
    assert report.smoke["offline"] is True
    assert report.smoke["blocked_request_count"] == 1
    assert report.smoke["blocked_requests"][0]["method"] == "POST"
    assert "dead_primary_cta" not in {issue.code for issue in report.issues}


def test_ready_selector_waits_for_late_spa_content(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    report = audit(
        served.url("late.html"),
        settings=Settings(
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            ready_selector="#ready",
            settle_ms=0,
        ),
        output_dir=tmp_path,
    )
    assert "load_error" not in {issue.code for issue in report.issues}
    assert "ready_selector_not_found" not in {issue.code for issue in report.issues}


def test_missing_ready_selector_has_actionable_diagnostic(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    report = audit(
        served.url("clean.html"),
        settings=Settings(
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            ready_selector="#missing",
            settle_ms=0,
            timeout_ms=500,
        ),
        output_dir=tmp_path,
    )
    assert "ready_selector_not_found" in {issue.code for issue in report.issues}


def test_http_error_short_circuits_secondary_noise(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    report = audit(
        served.url("not-found.html"),
        settings=Settings(
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            settle_ms=0,
        ),
        output_dir=tmp_path,
    )
    assert [issue.code for issue in report.issues] == ["http_error"]
    assert report.smoke["performed"] is False


def test_known_console_and_request_noise_can_be_ignored(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    report = audit(
        served.url("broken.html"),
        settings=Settings(
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            settle_ms=0,
            ignore_console_patterns=(
                "bad production log",
                r"Failed to load resource:.*404",
            ),
            ignore_request_patterns=(r"/missing\.png$",),
        ),
        output_dir=tmp_path,
    )
    codes = {issue.code for issue in report.issues}
    assert "console_error" not in codes
    assert "resource_failure" not in codes
    assert "broken_image" in codes
    assert not any(
        "bad production log" in message for message in report.viewports[0]["console_errors"]
    )


def test_failed_success_assertion_overrides_generic_dom_change(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    report = audit(
        served.url("clean.html"),
        settings=Settings(
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            settle_ms=0,
            smoke_success_selector="#missing-success",
        ),
        output_dir=tmp_path,
    )
    assert report.smoke["changed"] is True
    assert report.smoke["success"] is False
    assert [issue.code for issue in report.issues] == ["cta_assertion_failed"]


def test_success_selector_must_transition_to_visible(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    report = audit(
        served.url("clean.html"),
        settings=Settings(
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            settle_ms=0,
            smoke_success_selector="#start",
        ),
        output_dir=tmp_path,
    )
    assertion = report.smoke["assertions"][0]
    assert assertion["matchedBefore"] is True
    assert assertion["matchedAfter"] is True
    assert assertion["matched"] is False
    assert report.smoke["success"] is False


def test_success_assertions_survive_full_page_navigation(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    report = audit(
        served.url("navigate.html"),
        settings=Settings(
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            settle_ms=0,
            smoke_mode="live",
            smoke_success_selector="#done",
            smoke_success_url_pattern=r"/after\.html$",
        ),
        output_dir=tmp_path,
    )
    assert report.smoke["execution_lost"] is True
    assert report.smoke["success"] is True
    assert all(assertion["matched"] for assertion in report.smoke["assertions"])
    assert "cta_assertion_failed" not in {issue.code for issue in report.issues}


def test_bounded_smoke_flow_fills_clicks_and_verifies_outcome(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    report = audit(
        served.url("flow.html"),
        settings=Settings(
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            settle_ms=0,
            smoke_settle_ms=10,
            smoke_flow=(
                SmokeStep("fill", selector="#email", value="qa@example.com"),
                SmokeStep("click", selector="#continue"),
                SmokeStep("expect_visible", selector="#success"),
                SmokeStep("expect_url", pattern=r"#complete$"),
            ),
        ),
        output_dir=tmp_path,
    )
    assert report.smoke["kind"] == "flow"
    assert report.smoke["success"] is True
    assert report.smoke["assertion_required"] is True
    assert [step["status"] for step in report.smoke["steps"]] == ["passed"] * 4
    assert all(assertion["matched"] for assertion in report.smoke["assertions"])
    assert not {
        "smoke_flow_step_failed",
        "smoke_flow_assertion_failed",
        "smoke_flow_page_error",
    } & {issue.code for issue in report.issues}
    assert "qa@example.com" not in json.dumps(report.to_dict())


def test_bounded_smoke_flow_reports_failed_assertion_without_input_value(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    report = audit(
        served.url("flow.html"),
        settings=Settings(
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            settle_ms=0,
            timeout_ms=500,
            smoke_settle_ms=10,
            smoke_flow=(
                SmokeStep("fill", selector="#email", value="do-not-persist"),
                SmokeStep("fill", selector="#email", value=""),
                SmokeStep("click", selector="#continue"),
                SmokeStep("expect_visible", selector="#success"),
            ),
        ),
        output_dir=tmp_path,
    )
    assert report.smoke["success"] is False
    assert report.smoke["failedStep"]["action"] == "expect_visible"
    assert "smoke_flow_assertion_failed" in {issue.code for issue in report.issues}
    assert "do-not-persist" not in json.dumps(report.to_dict())


def test_bounded_smoke_flow_names_the_failed_action(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    report = audit(
        served.url("flow.html"),
        settings=Settings(
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            settle_ms=0,
            timeout_ms=500,
            smoke_settle_ms=0,
            smoke_flow=(
                SmokeStep("click", selector="#missing-action"),
                SmokeStep("expect_visible", selector="#success"),
            ),
        ),
        output_dir=tmp_path,
    )
    failed = next(issue for issue in report.issues if issue.code == "smoke_flow_step_failed")
    assert report.smoke["observed_effect"] is False
    assert "step 1 (click)" in failed.message
    assert failed.evidence["step"]["selector"] == "#missing-action"


def test_bounded_smoke_flow_surfaces_page_errors(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    report = audit(
        served.url("flow-error.html"),
        settings=Settings(
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            settle_ms=0,
            smoke_settle_ms=50,
            smoke_flow=(
                SmokeStep("click", selector="#boom"),
                SmokeStep("expect_visible", selector="#done"),
            ),
        ),
        output_dir=tmp_path,
    )
    assert report.smoke["success"] is True
    assert "smoke_flow_page_error" in {issue.code for issue in report.issues}


def test_accessibility_profile_adds_deterministic_checks(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    accessibility_codes = {
        "aria_hidden_focusable",
        "control_missing_name",
        "duplicate_id",
        "heading_level_skip",
        "image_missing_alt",
        "missing_html_lang",
        "positive_tabindex",
    }
    url = served.url("inaccessible.html")
    baseline = audit(
        url,
        settings=Settings(
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            settle_ms=0,
            profile="baseline",
        ),
        output_dir=tmp_path / "baseline",
        smoke=False,
    )
    accessibility = audit(
        url,
        settings=Settings(
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            settle_ms=0,
            profile="accessibility",
        ),
        output_dir=tmp_path / "accessibility",
        smoke=False,
    )
    assert not accessibility_codes & {issue.code for issue in baseline.issues}
    assert accessibility_codes <= {issue.code for issue in accessibility.issues}
    snapshot = accessibility.viewports[0]["measurements"]["accessibility"]
    assert snapshot["lang"] == ""
    assert snapshot["imagesMissingAlt"]


def test_accessibility_profile_accepts_clean_page(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    report = audit(
        served.url("clean.html"),
        settings=Settings(
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            settle_ms=0,
            profile="accessibility",
        ),
        output_dir=tmp_path,
        smoke=False,
    )
    assert not {
        "aria_hidden_focusable",
        "control_missing_name",
        "duplicate_id",
        "heading_level_skip",
        "image_missing_alt",
        "missing_html_lang",
        "missing_page_title",
        "positive_tabindex",
    } & {issue.code for issue in report.issues}


def test_smoke_runs_in_every_configured_viewport(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    report = audit(
        served.url("clean.html"),
        settings=Settings(
            viewports=(
                Viewport(390, 844, "mobile", mobile=True),
                Viewport(1280, 800, "desktop"),
            ),
            settle_ms=0,
            smoke_scope="all",
            smoke_settle_ms=10,
            smoke_success_selector="#result",
            smoke_success_url_pattern=r"#started$",
        ),
        output_dir=tmp_path,
    )
    assert [run["viewport"] for run in report.smoke_runs] == ["mobile", "desktop"]
    assert all(run["success"] for run in report.smoke_runs)
    assert {run["assertion_required"] for run in report.smoke_runs} == {False}


def test_shadow_dom_cta_and_dom_evidence_are_actionable(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    report = audit(
        served.url("shadow.html"),
        settings=Settings(
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            settle_ms=0,
            smoke_settle_ms=10,
            smoke_success_selector="#shadow-result",
        ),
        output_dir=tmp_path,
    )
    assert report.smoke["found"] is True
    assert report.smoke["success"] is True
    measurements = report.viewports[0]["measurements"]
    assert "#shadow-image" in {image["selector"] for image in measurements["brokenImages"]}
    assert "#shadow-small" in {row["selector"] for row in measurements["tinyFonts"]}
    assert "#shadow-cta" in {row["selector"] for row in measurements["smallTargets"]}


def test_accessibility_checks_cross_shadow_boundaries(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    report = audit(
        served.url("shadow.html"),
        settings=Settings(
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            settle_ms=0,
            profile="accessibility",
        ),
        output_dir=tmp_path,
        smoke=False,
    )
    missing_names = next(issue for issue in report.issues if issue.code == "control_missing_name")
    missing_alt = next(issue for issue in report.issues if issue.code == "image_missing_alt")
    assert "#shadow-unnamed" in {row["selector"] for row in missing_names.evidence["controls"]}
    assert "#shadow-image" in {row["selector"] for row in missing_alt.evidence["images"]}


def test_network_idle_timeout_is_recorded_without_hiding_page_results(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    report = audit(
        served.url("network-active.html"),
        settings=Settings(
            viewports=(Viewport(390, 844, "mobile", mobile=True),),
            settle_ms=0,
            timeout_ms=1_200,
            wait_for_network_idle=True,
        ),
        output_dir=tmp_path,
        smoke=False,
    )
    readiness = report.viewports[0]["readiness"]
    assert readiness["network_idle_requested"] is True
    assert readiness["network_idle_reached"] is False
    assert readiness["network_idle_timed_out"] is True
    assert "network_idle_timeout" in {issue.code for issue in report.issues}


def test_slow_load_event_keeps_rendered_page_auditable(tmp_path: Path) -> None:
    html = b"""<!doctype html><html lang="en"><head>
<meta name="viewport" content="width=device-width">
<title>Slow asset</title><style>
body{margin:0;font:16px/1.5 system-ui}main{padding:32px}img{width:80px;height:80px}
</style></head><body><main><h1>Rendered before load</h1>
<p>This page remains auditable while a late image is still pending.</p>
<img src="/slow.svg" width="80" height="80" alt="Delayed sample">
</main></body></html>"""
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80"></svg>'

    class SlowHandler(http.server.BaseHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def do_GET(self) -> None:
            if self.path == "/":
                body = html
                content_type = "text/html; charset=utf-8"
            elif self.path == "/slow.svg":
                time.sleep(1.2)
                body = svg
                content_type = "image/svg+xml"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                self.wfile.write(body)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), SlowHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        report = audit(
            f"http://127.0.0.1:{server.server_address[1]}/",
            settings=Settings(
                viewports=(Viewport(390, 844, "mobile", mobile=True),),
                settle_ms=0,
                timeout_ms=500,
            ),
            output_dir=tmp_path,
            smoke=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    readiness = report.viewports[0]["readiness"]
    assert readiness["dom_content_loaded"] is True
    assert readiness["load_event_reached"] is False
    assert readiness["load_event_timed_out"] is True
    assert [(issue.code, issue.severity) for issue in report.issues] == [
        ("slow_load_event", "warning")
    ]
    assert report.viewports[0]["status"] == "ok"


def test_authenticated_preview_inputs_work_together(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    (site / "private.html").write_text(
        """<!doctype html><html lang="en"><head><meta name="viewport"
content="width=device-width"><title>Private preview</title><style>
body{margin:0;font:16px/1.5 system-ui}main{padding:32px}</style></head>
<body><main><h1>Authenticated preview</h1><p>All three access controls passed.</p>
</main></body></html>""",
        encoding="utf-8",
    )
    expected_auth = "Basic " + base64.b64encode(b"preview-user:preview-password").decode()

    class GuardedHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(site), **kwargs)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def do_GET(self) -> None:
            valid = (
                self.headers.get("Authorization") == expected_auth
                and self.headers.get("X-Preview-Key") == "agent-key"
                and "session=ready" in (self.headers.get("Cookie") or "")
            )
            if not valid:
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="preview"')
                self.end_headers()
                return
            super().do_GET()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), GuardedHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/private.html"
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "cookies": [
                    {
                        "name": "session",
                        "value": "ready",
                        "domain": "127.0.0.1",
                        "path": "/",
                        "expires": -1,
                        "httpOnly": False,
                        "secure": False,
                        "sameSite": "Lax",
                    }
                ],
                "origins": [],
            }
        ),
        encoding="utf-8",
    )
    viewports = (Viewport(390, 844, "mobile", mobile=True),)
    try:
        denied = audit(
            url,
            settings=Settings(viewports=viewports, settle_ms=0),
            output_dir=tmp_path / "denied",
            smoke=False,
        )
        assert {issue.code for issue in denied.issues} == {"http_error"}

        allowed = audit(
            url,
            settings=Settings(
                viewports=viewports,
                settle_ms=0,
                storage_state=str(state),
                extra_http_headers={"X-Preview-Key": "agent-key"},
                http_username="preview-user",
                http_password="preview-password",
            ),
            output_dir=tmp_path / "allowed",
            smoke=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert allowed.viewports[0]["title"] == "Private preview"
    assert "http_error" not in {issue.code for issue in allowed.issues}
    assert allowed.settings["extra_http_headers"] == {"X-Preview-Key": "<redacted>"}
    assert "agent-key" not in json.dumps(allowed.to_dict())


def test_concurrent_agent_invocations_have_isolated_reports(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    target = served.url("clean.html")
    commands = []
    for name in ("agent-a", "agent-b"):
        output = tmp_path / name
        commands.append(
            (
                output,
                [
                    sys.executable,
                    "-m",
                    "ego_webqa",
                    target,
                    "--out",
                    str(output),
                    "--viewports",
                    "390x844:mobile",
                    "--no-smoke",
                    "--json",
                ],
            )
        )
    processes = [
        subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _, command in commands
    ]
    completed = [process.communicate(timeout=60) for process in processes]
    for (output, _), process, (stdout, stderr) in zip(
        commands,
        processes,
        completed,
        strict=True,
    ):
        assert process.returncode == 0, stderr or stdout
        payload = json.loads((output / "report.json").read_text(encoding="utf-8"))
        assert payload["schema_version"] == "1.0"
        assert payload["screenshots"] == ["screenshots/mobile.png"]
        assert (output / payload["screenshots"][0]).is_file()


def test_text_scaling_reports_layout_break_with_scale_evidence(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    viewport = Viewport(390, 844, "mobile-150", mobile=True, text_scale=1.5)
    broken = audit(
        served.url("text-scale-break.html"),
        settings=Settings(viewports=(viewport,), settle_ms=0),
        output_dir=tmp_path / "text-break",
        smoke=False,
    )
    assert {issue.code for issue in broken.issues} == {"text_scale_layout_break"}
    assert broken.issues[0].evidence["text_scale"] == 1.5
    assert broken.viewports[0]["viewport"]["text_scale"] == 1.5
    assert broken.viewports[0]["measurements"]["environment"]["textScale"] == 1.5

    clean = audit(
        served.url("text-scale-clean.html"),
        settings=Settings(viewports=(viewport,), settle_ms=0),
        output_dir=tmp_path / "text-clean",
        smoke=False,
    )
    assert clean.issues == []


def test_default_matrix_audits_eight_narrow_variants_with_unique_evidence(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    report = audit(
        served.url("clean.html"),
        settings=Settings(settle_ms=0),
        output_dir=tmp_path / "default-matrix",
        smoke=False,
    )
    assert len(report.viewports) == 8
    assert len(report.screenshots) == 8
    assert len(set(report.screenshots)) == 8
    assert report.issues == []
    assert {
        (
            row["viewport"]["width"],
            row["viewport"]["text_scale"],
            row["viewport"]["safe_area_bottom_px"],
        )
        for row in report.viewports
    } == {
        (width, text_scale, safe_area_bottom_px)
        for width in (360, 390)
        for text_scale in (1.0, 1.5)
        for safe_area_bottom_px in (0, 34)
    }


def test_bottom_safe_area_penetration_has_clean_control(
    served: LocalServer,
    tmp_path: Path,
) -> None:
    viewport = Viewport(
        390,
        844,
        "mobile-safe-34",
        mobile=True,
        safe_area_bottom_px=34,
    )
    broken = audit(
        served.url("safe-area-break.html"),
        settings=Settings(viewports=(viewport,), settle_ms=0),
        output_dir=tmp_path / "safe-break",
        smoke=False,
    )
    assert {issue.code for issue in broken.issues} == {"bottom_safe_area_penetration"}
    assert broken.issues[0].evidence["elements"][0]["required_gap_px"] == 34
    assert broken.issues[0].hint == (
        "Reserve max(34px, env(safe-area-inset-bottom)) around bottom controls."
    )
    assert broken.viewports[0]["viewport"]["safe_area_bottom_px"] == 34

    clean = audit(
        served.url("safe-area-clean.html"),
        settings=Settings(viewports=(viewport,), settle_ms=0),
        output_dir=tmp_path / "safe-clean",
        smoke=False,
    )
    assert clean.issues == []
