from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from ego_webqa import __version__

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "docs" / "demo"
LEDGER = DEMO / "data" / "repair-ledger.json"
DOGFOOD = ROOT / "dogfood-results"


class LocalReferences(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        attribute = "src" if tag in {"img", "script"} else "href" if tag in {"link", "a"} else None
        if attribute and (reference := values.get(attribute)):
            self.references.append(reference)


def load_agent_summary(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


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
    assert "data/repair-ledger.json" in local_references
    for reference in local_references:
        assert (DEMO / urlsplit(reference).path).is_file(), reference


def test_repair_ledger_matches_the_recorded_baseline_before_and_after() -> None:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))

    assert ledger["profile"] == "baseline"
    assert ledger["browser"] == "chrome"
    assert ledger["viewport_count"] == 8
    assert ledger["thresholds_relaxed"] == 0
    assert len(ledger["cases"]) == 3

    for case in ledger["cases"]:
        case_id = f"egohub-work-{case['id']}"
        before = load_agent_summary(
            DOGFOOD / "20261031-profile-baseline" / "cases" / case_id / "agent_summary.json"
        )
        after = load_agent_summary(
            DOGFOOD / "20261031-post-footer-repair" / "cases" / case_id / "agent_summary.json"
        )
        before_root = before["failed_items"][0]
        match = re.search(r"page is (\d+)px wider", before_root["problem"])

        assert case["before"]["status"] == before["status"] == "fail"
        assert case["before"]["blocks"] == before["summary"]["total_block"]
        assert case["before"]["warnings"] == before["summary"]["total_warn"]
        assert case["before"]["issue_occurrences"] == (
            before["summary"]["total_block"] + before["summary"]["total_warn"]
        )
        assert case["finding"]["dimension"] == before_root["dimension_id"]
        assert match is not None
        assert case["finding"]["measured_px"] == int(match.group(1))
        assert case["after"]["status"] == after["status"] == "pass"
        assert case["after"]["blocks"] == after["summary"]["total_block"] == 0
        assert case["after"]["warnings"] == after["summary"]["total_warn"] == 0
        assert case["after"]["issue_occurrences"] == 0
        assert case["after"]["duration_ms"] == after["summary"]["duration_ms"]
        assert after["summary"]["overridden_dimensions"] == 0
        assert after["summary"]["downgraded_blocks"] == 0

        assert (DEMO / "assets" / "production" / "before" / f"{case['id']}.png").is_file()
        assert (DEMO / "assets" / "production" / "after" / f"{case['id']}.png").is_file()


def test_negative_controls_are_clean_pages_not_invented_claims() -> None:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))

    for control in ledger["controls"]:
        source = load_agent_summary(
            DOGFOOD
            / "20261031-post-footer-repair"
            / "cases"
            / f"egohub-{control['id']}"
            / "agent_summary.json"
        )
        assert control["status"] == source["status"] == "pass"
        assert control["blocks"] == source["summary"]["total_block"] == 0
        assert control["warnings"] == source["summary"]["total_warn"] == 0
        assert control["duration_ms"] == source["summary"]["duration_ms"]


def test_corpus_summary_comes_from_the_post_repair_result() -> None:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    result = json.loads(
        (DOGFOOD / "20261031-post-footer-repair" / "result.json").read_text(encoding="utf-8")
    )
    metrics = result["metrics"]

    assert ledger["corpus"]["cases"] == metrics["cases"]
    assert ledger["corpus"]["successful_audits"] == metrics["successful_audits"]
    assert ledger["corpus"]["runtime_errors"] == metrics["runtime_errors"]
    assert ledger["corpus"]["profile"] == result["manifest"]["qa_profiles"][0]
    assert ledger["corpus"]["browser"] == result["environment"]["browser_channel"]
    for status in ("pass", "warn", "fail"):
        assert ledger["corpus"][status] == metrics["statuses"][status]


def test_demo_leads_with_the_repair_chain_and_scope_boundary() -> None:
    html = (DEMO / "index.html").read_text(encoding="utf-8")
    normalized = " ".join(html.split())

    assert "Failure, location, repair, proof" in normalized
    assert "thresholds relaxed" in normalized
    assert "A gate that never passes is not a gate." in normalized
    assert "What this run proves" in normalized
    assert "What it does not prove" in normalized
    assert 'data-case="tetris"' in html
    assert 'data-case="word-quiz"' in html
    assert 'data-case="vocabulary"' in html


def test_demo_llms_txt_declares_the_agent_discovery_contract() -> None:
    text = (DEMO / "llms.txt").read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert text.startswith("# ego-webqa\n")
    assert "`ego-webqa setup`" in text
    assert "`uvx ego-webqa mcp`" in text
    assert "`audit_web_page`" in text
    assert "https://roy32172310.github.io/qa/" in text
    assert "does not prove business-flow correctness" in normalized
    assert "does not accept arbitrary URLs for server-side auditing" in normalized


def test_feedback_template_tracks_the_current_version() -> None:
    template = (ROOT / ".github" / "ISSUE_TEMPLATE" / "result-feedback.yml").read_text(
        encoding="utf-8"
    )

    assert f'placeholder: "{__version__}"' in template


def test_pages_workflow_publishes_only_the_static_demo() -> None:
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")

    assert "path: docs/demo" in workflow
    assert "actions/upload-pages-artifact@v4" in workflow
    assert "actions/deploy-pages@v5" in workflow
    assert "enablement: true" in workflow
