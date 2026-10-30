from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts import package_agensi


def test_agensi_archive_is_reproducible_and_complete() -> None:
    first, first_members = package_agensi.build_archive()
    second, second_members = package_agensi.build_archive()

    assert first == second
    assert first_members == second_members
    assert set(package_agensi.REQUIRED_FILES) <= {
        member.removeprefix(f"{package_agensi.ARCHIVE_ROOT}/") for member in first_members
    }

    with ZipFile(io.BytesIO(first)) as archive:
        assert archive.testzip() is None
        config = json.loads(archive.read(f"{package_agensi.ARCHIVE_ROOT}/mcp-config.example.json"))
        assert config["mcpServers"]["ego-webqa"]["args"] == [
            "--from",
            f"ego-webqa=={package_agensi._project_version()}",
            "ego-webqa",
            "mcp",
        ]


def test_agensi_package_command_writes_and_checks_archive(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "web-delivery-qa-gate.zip"
    assert package_agensi.main(["--out", str(output)]) == 0
    first_digest = hashlib.sha256(output.read_bytes()).hexdigest()
    assert package_agensi.main(["--out", str(output)]) == 0
    assert hashlib.sha256(output.read_bytes()).hexdigest() == first_digest
    assert package_agensi.main(["--out", str(output), "--check"]) == 0

    output.write_bytes(b"stale")
    assert package_agensi.main(["--out", str(output), "--check"]) == 1
    assert "stale or missing archive" in capsys.readouterr().err
