from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "docs" / "demo"
VARIANTS = (
    "mobile-360-100-safe0",
    "mobile-360-100-safe34",
    "mobile-360-150-safe0",
    "mobile-360-150-safe34",
    "mobile-390-100-safe0",
    "mobile-390-100-safe34",
    "mobile-390-150-safe0",
    "mobile-390-150-safe34",
)


class LocalReferences(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        attribute = "src" if tag in {"img", "script"} else "href" if tag in {"link", "a"} else None
        if attribute and (reference := values.get(attribute)):
            self.references.append(reference)


def test_demo_references_existing_local_assets() -> None:
    parser = LocalReferences()
    parser.feed((DEMO / "index.html").read_text(encoding="utf-8"))

    local_references = {
        reference
        for reference in parser.references
        if not reference.startswith(("#", "data:", "http:", "https:"))
    }

    assert "styles.css" in local_references
    assert "app.js" in local_references
    for reference in local_references:
        assert (DEMO / urlsplit(reference).path).is_file(), reference


def test_demo_contains_every_parameter_capture() -> None:
    for variant in VARIANTS:
        assert (DEMO / "assets" / "before" / f"{variant}.png").is_file()
        assert (DEMO / "assets" / "after" / f"{variant}.png").is_file()


def test_demo_json_is_the_verified_dogfood_run() -> None:
    before = json.loads((DEMO / "data" / "before-agent-summary.json").read_text(encoding="utf-8"))
    after = json.loads((DEMO / "data" / "after-agent-summary.json").read_text(encoding="utf-8"))

    assert before["status"] == "fail"
    assert before["summary"]["total_block"] == 10
    assert before["summary"]["unique_root_causes"] == 3
    assert after["status"] == "warn"
    assert after["summary"]["total_block"] == 0
    assert after["summary"]["unique_root_causes"] == 1


def test_demo_llms_txt_declares_the_agent_discovery_contract() -> None:
    text = (DEMO / "llms.txt").read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert text.startswith("# ego-webqa\n")
    assert "`python -m playwright install chromium`" in text
    assert "`uvx ego-webqa mcp`" in text
    assert "`audit_web_page`" in text
    assert "https://roy32172310.github.io/qa/" in text
    assert "does not prove business-flow correctness" in normalized
    assert "does not accept arbitrary URLs for server-side auditing" in normalized


def test_pages_workflow_publishes_only_the_static_demo() -> None:
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")

    assert "path: docs/demo" in workflow
    assert "actions/upload-pages-artifact@v3" in workflow
    assert "actions/deploy-pages@v4" in workflow
    assert "enablement: true" in workflow
