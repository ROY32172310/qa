from __future__ import annotations

from pathlib import Path
from urllib.request import urlopen

import pytest

from ego_webqa.server import LocalServer


def test_local_server_serves_directory(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<h1>hello</h1>", encoding="utf-8")
    with LocalServer(tmp_path) as server:
        assert server.port > 0
        content = urlopen(server.url(), timeout=2).read().decode()
        assert "hello" in content


def test_local_server_rejects_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        LocalServer(tmp_path / "missing")


def test_local_server_encodes_unsafe_filenames(tmp_path: Path) -> None:
    path = tmp_path / "space name#1.html"
    path.write_text("<h1>encoded</h1>", encoding="utf-8")
    with LocalServer(tmp_path) as server:
        url = server.url(path.name)
        assert "%20" in url
        assert "%23" in url
        assert "encoded" in urlopen(url, timeout=2).read().decode()
