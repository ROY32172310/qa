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
    assert Path(report.screenshots[0]).is_file()
    environment = report.viewports[0]["measurements"]["environment"]
    assert report.viewports[0]["measurements"]["viewport"]["width"] == 390
    assert "Mobile" in environment["userAgent"]
    assert environment["maxTouchPoints"] > 0
    assert environment["coarsePointer"] is True


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
    assert {"horizontal_overflow", "console_error", "unreadable_font", "broken_image"} <= codes


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
            timeout_ms=200,
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
