from __future__ import annotations

from pathlib import Path

from ego_webqa import __version__

ROOT = Path(__file__).resolve().parents[1]
AGENSI = ROOT / "integrations" / "agensi"


def test_agensi_skill_tracks_the_current_release_and_capabilities() -> None:
    skill = (AGENSI / "web-delivery-qa-gate" / "SKILL.md").read_text(encoding="utf-8")

    assert f"The tested release is `{__version__}`." in skill
    assert "ego-webqa doctor --json" in skill
    assert "--preset quick" in skill
    assert "--baseline-report" in skill
    assert "--smoke-flow-name NAME" in skill or "--config PATH" in skill
    assert "feedback_bundle.json" in skill
    assert "--print-schema report" in skill


def test_agensi_reference_contract_covers_release_080_integrations() -> None:
    reference = (AGENSI / "web-delivery-qa-gate" / "references" / "report-contract.md").read_text(
        encoding="utf-8"
    )

    assert "`--preset quick`" in reference
    assert "`delta.json`" in reference
    assert "`new`, `persistent`, `changed`, or `resolved`" in reference
    assert "`feedback-bundle`" in reference
    assert "`doctor`" in reference
    assert "ego-webqa --print-schema agent-summary" in reference


def test_agensi_listing_uses_the_current_version_and_describes_new_controls() -> None:
    listing = (AGENSI / "LISTING.md").read_text(encoding="utf-8")

    assert f'python -m pip install "ego-webqa=={__version__}"' in listing
    assert "`quick` preset" in listing
    assert "baseline/delta gating" in listing
    assert "privacy-first feedback bundles" in listing
    assert "`1.0` JSON Schemas" in listing
