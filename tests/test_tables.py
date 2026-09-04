"""Test shared table rendering helpers."""

from __future__ import annotations

from tapmap.ui.tables import cell


def test_cell_default_tooltip_matches_displayed_text() -> None:
    """Without an explicit title, the tooltip defaults to the cell's own text."""
    result = cell("Firefox")

    assert result.children.title == "Firefox"
    assert result.children.children == "Firefox"


def test_cell_explicit_title_overrides_displayed_text() -> None:
    """An explicit title is used verbatim, independent of the displayed text."""
    result = cell("Retrieving...", title="/opt/app.exe")

    assert result.children.title == "/opt/app.exe"
    assert result.children.children == "Retrieving..."


def test_cell_empty_text_has_no_tooltip() -> None:
    """An empty cell has no tooltip - an empty title="" would render as a blank hover box."""
    result = cell("")

    assert result.children.title is None
