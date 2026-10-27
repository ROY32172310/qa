from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ego_webqa import cli
from ego_webqa.models import AuditReport


def _report(status: str = "pass") -> AuditReport:
    return AuditReport(
        target="http://example.test/",
        status=status,  # type: ignore[arg-type]
        issues=[],
        viewports=[],
        smoke={},
        screenshots=[],
        started_at="2026-10-27T00:00:00+00:00",
        duration_ms=1,
        settings={},
    )


def test_cli_usage_errors(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([]) == 2
    assert cli.main(["https://example.com", "--dir", "."]) == 2
    assert "provide a URL or --dir" in capsys.readouterr().err


def test_cli_invalid_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "bad.json"
    path.write_text("[]", encoding="utf-8")
    assert cli.main(["https://example.com", "--config", str(path)]) == 2
    assert "invalid configuration" in capsys.readouterr().err


def test_cli_json_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _report()

    def fake_audit(*args: Any, **kwargs: Any) -> AuditReport:
        del args, kwargs
        return report

    monkeypatch.setattr(cli, "audit", fake_audit)
    monkeypatch.setattr(
        cli,
        "write_reports",
        lambda *args, **kwargs: {"json": "report.json"},
    )
    assert cli.main(["https://example.com", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "pass"


def test_cli_local_directory_and_fail_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "index.html").write_text("<h1>ok</h1>", encoding="utf-8")
    seen: dict[str, str] = {}

    def fake_audit(target: str, **kwargs: Any) -> AuditReport:
        del kwargs
        seen["target"] = target
        return _report("fail")

    monkeypatch.setattr(cli, "audit", fake_audit)
    monkeypatch.setattr(
        cli,
        "write_reports",
        lambda *args, **kwargs: {"json": "report.json"},
    )
    assert cli.main(["--dir", str(tmp_path), "--no-smoke"]) == 1
    assert seen["target"].startswith("http://127.0.0.1:")
