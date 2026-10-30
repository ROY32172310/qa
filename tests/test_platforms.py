from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from ego_webqa import platforms


def test_platform_path_adapter_preserves_posix_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(platforms, "Path", PurePosixPath)

    assert platforms.native_path("/missing/browser") == PurePosixPath("/missing/browser")
    assert str(platforms.native_path("/missing/browser")).endswith("missing/browser")


def test_platform_path_adapter_preserves_windows_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(platforms, "Path", PureWindowsPath)

    assert platforms.native_path("/missing/browser") == PureWindowsPath("/missing/browser")
    assert str(platforms.native_path("/missing/browser")).endswith(r"missing\browser")


@pytest.mark.parametrize(
    ("system", "expected"),
    [
        ("Linux", True),
        ("Windows", False),
        ("Darwin", False),
    ],
)
def test_linux_dependency_boundary(
    monkeypatch: pytest.MonkeyPatch,
    system: str,
    expected: bool,
) -> None:
    monkeypatch.setattr(platforms.platform, "system", lambda: system)

    assert platforms.is_linux() is expected


def test_native_path_uses_the_stdlib_path_type() -> None:
    assert platforms.native_path("relative/file") == Path("relative/file")
