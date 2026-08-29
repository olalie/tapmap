"""Test tray menu behavior."""

from __future__ import annotations

from pathlib import Path

from tapmap.tray import create_tray_icon

_ICON_PATH = Path(__file__).resolve().parent.parent / "src" / "tapmap" / "assets" / "tapmap.ico"


def test_create_tray_icon_menu_is_open_separator_quit() -> None:
    """Create the tray menu with Open, separator, and Quit."""
    icon = create_tray_icon(
        icon_path=_ICON_PATH,
        tooltip="TapMap",
        on_open=lambda: None,
        on_quit=lambda: None,
    )
    assert icon is not None
    items = list(icon.menu)
    assert [item.text for item in items] == ["Open TapMap", "- - - -", "Quit TapMap"]


def test_create_tray_icon_open_item_is_the_default_action() -> None:
    """Use Open TapMap as the default tray action."""
    icon = create_tray_icon(
        icon_path=_ICON_PATH,
        tooltip="TapMap",
        on_open=lambda: None,
        on_quit=lambda: None,
    )
    assert icon is not None
    open_item = next(item for item in icon.menu if item.text == "Open TapMap")
    assert open_item.default is True


def test_create_tray_icon_open_item_calls_on_open() -> None:
    """Call the open callback from Open TapMap."""
    calls: list[str] = []
    icon = create_tray_icon(
        icon_path=_ICON_PATH,
        tooltip="TapMap",
        on_open=lambda: calls.append("open"),
        on_quit=lambda: None,
    )
    assert icon is not None
    open_item = next(item for item in icon.menu if item.text == "Open TapMap")

    open_item(icon)

    assert calls == ["open"]


def test_create_tray_icon_quit_item_calls_on_quit() -> None:
    """Call the quit callback from Quit TapMap."""
    calls: list[str] = []
    icon = create_tray_icon(
        icon_path=_ICON_PATH,
        tooltip="TapMap",
        on_open=lambda: None,
        on_quit=lambda: calls.append("quit"),
    )
    assert icon is not None
    quit_item = next(item for item in icon.menu if item.text == "Quit TapMap")

    quit_item(icon)

    assert calls == ["quit"]


def test_create_tray_icon_returns_none_when_icon_file_is_missing(tmp_path: Path) -> None:
    """Return no tray icon when tray creation fails."""
    icon = create_tray_icon(
        icon_path=tmp_path / "does-not-exist.ico",
        tooltip="TapMap",
        on_open=lambda: None,
        on_quit=lambda: None,
    )
    assert icon is None
