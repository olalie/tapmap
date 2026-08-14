"""Test the macOS bundle Info.plist reader against real constructed bundles."""

from __future__ import annotations

import plistlib
from pathlib import Path

import pytest

from tapmap.model.appinfo import macos_bundle_info


def _make_bundle(tmp_path: Path, *, name: str = "Foo.app", plist: dict | None = None) -> Path:
    """Create a minimal .app bundle under tmp_path and return its executable path."""
    contents = tmp_path / name / "Contents"
    macos_dir = contents / "MacOS"
    macos_dir.mkdir(parents=True)

    if plist is not None:
        with open(contents / "Info.plist", "wb") as f:
            plistlib.dump(plist, f)

    exe_path = macos_dir / "Foo"
    exe_path.write_bytes(b"")
    return exe_path


def test_find_bundle_root_locates_enclosing_app(tmp_path: Path) -> None:
    """The .app ancestor is found from a deeply nested executable path."""
    exe_path = _make_bundle(tmp_path)

    root = macos_bundle_info.find_bundle_root(str(exe_path))

    assert root == tmp_path / "Foo.app"


def test_get_bundle_info_reads_display_name_and_name(tmp_path: Path) -> None:
    """Both CFBundleDisplayName and CFBundleName are read when present."""
    exe_path = _make_bundle(
        tmp_path, plist={"CFBundleDisplayName": "Foo Display", "CFBundleName": "Foo"}
    )

    info = macos_bundle_info.get_bundle_info(str(exe_path))

    assert info["CFBundleDisplayName"] == "Foo Display"
    assert info["CFBundleName"] == "Foo"


def test_get_bundle_info_missing_display_name_is_none(tmp_path: Path) -> None:
    """CFBundleDisplayName is None when the plist doesn't have it (e.g. Firefox's real plist)."""
    exe_path = _make_bundle(tmp_path, plist={"CFBundleName": "Foo"})

    info = macos_bundle_info.get_bundle_info(str(exe_path))

    assert info["CFBundleDisplayName"] is None
    assert info["CFBundleName"] == "Foo"


def test_get_bundle_info_returns_empty_for_bare_executable(tmp_path: Path) -> None:
    """A bare executable with no enclosing .app yields no bundle info at all."""
    exe_path = tmp_path / "bin" / "foo"
    exe_path.parent.mkdir(parents=True)
    exe_path.write_bytes(b"")

    assert macos_bundle_info.get_bundle_info(str(exe_path)) == {}


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(None, id="missing"),
        pytest.param(b"not a plist at all", id="malformed-binary"),
        pytest.param(b"<?xml version='1.0'?><plist><dict><key>a</key></plist>", id="malformed-xml"),
    ],
)
def test_get_bundle_info_degrades_cleanly_on_bad_plist(
    tmp_path: Path, content: bytes | None
) -> None:
    """A missing or unparseable Info.plist degrades to empty, not an exception."""
    exe_path = _make_bundle(tmp_path, plist=None)
    if content is not None:
        plist_path = exe_path.parent.parent / "Info.plist"
        plist_path.write_bytes(content)

    assert macos_bundle_info.get_bundle_info(str(exe_path)) == {}
