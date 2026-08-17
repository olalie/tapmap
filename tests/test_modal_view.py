"""Tests for ModalTextBuilder.for_click."""

from dash import html

from tapmap.ui.modal_view import ModalTextBuilder


def _click_data(idx: int = 0) -> dict:
    return {
        "points": [
            {"customdata": {"kind": "geo_point", "idx": idx}, "lon": 1.0, "lat": 2.0}
        ]
    }


def _builder() -> ModalTextBuilder:
    return ModalTextBuilder(app_name="TapMap", app_version="1.0", app_author="Author")


def test_for_click_does_not_prepend_its_own_coordinate_line() -> None:
    """for_click renders detail as-is; it no longer prepends its own lon/lat line.

    The Technical Details view's own 'Coordinates:' line is now built by
    cache_view.py as part of detail itself, not injected here.
    """
    view = {"details": {"0": "Location: US\nSomething"}}

    result = _builder().for_click(_click_data(), view, is_docker=False)

    assert isinstance(result, html.Pre)
    rendered = "".join(c if isinstance(c, str) else c.children for c in result.children)
    assert "lon=" not in rendered
    assert "lat=" not in rendered


def test_for_click_renders_color_span_as_html_span() -> None:
    """Embedded '<span style=color>' markup becomes a real colored html.Span, not literal text."""
    detail = 'Network operator: Org A\n    <span style="color:#00ff66">■</span> App A'
    view = {"details": {"0": detail}}

    result = _builder().for_click(_click_data(), view, is_docker=False)

    children = result.children
    span = next(c for c in children if isinstance(c, html.Span))
    assert span.children == "■"
    assert span.style == {"color": "#00ff66"}
    assert not any(isinstance(c, str) and "<span" in c for c in children)


def test_for_click_renders_multi_character_color_span_as_html_span() -> None:
    """A multi-character colored span (e.g. verification status text) renders as one html.Span."""
    detail = (
        'Firefox (Mozilla Corporation, '
        '<span style="color:#00ff66">Trusted and signed</span>)'
    )
    view = {"details": {"0": detail}}

    result = _builder().for_click(_click_data(), view, is_docker=False)

    children = result.children
    span = next(c for c in children if isinstance(c, html.Span))
    assert span.children == "Trusted and signed"
    assert span.style == {"color": "#00ff66"}
    assert "Firefox (Mozilla Corporation, " in children
    assert ")" in children


def test_for_click_renders_exe_tag_as_clickable_span_with_tooltip() -> None:
    """Embedded '<exe full=...>' markup becomes a tooltip-bearing, clickable html.Span."""
    full_path = r"C:\Program Files\WindowsApps\...\MicrosoftStartFeedProvider.exe"
    detail = f'Executable:  <exe full="{full_path}">C:\\...\\Feed.exe</exe>'
    view = {"details": {"0": detail}}

    result = _builder().for_click(_click_data(), view, is_docker=False)

    children = result.children
    span = next(c for c in children if isinstance(c, html.Span))
    assert span.children == "C:\\...\\Feed.exe"
    assert span.title == full_path
    assert span.id == {"type": "reveal-exe", "path": full_path, "idx": 0}
    assert span.n_clicks == 0
    assert not any(isinstance(c, str) and "<exe" in c for c in children)


def test_for_click_assigns_distinct_ids_to_multiple_exe_tags() -> None:
    """Multiple executable entries in one panel get unique pattern-matching ids."""
    detail = (
        '<exe full="C:\\a.exe">C:\\a.exe</exe>\n'
        '<exe full="C:\\b.exe">C:\\b.exe</exe>'
    )
    view = {"details": {"0": detail}}

    result = _builder().for_click(_click_data(), view, is_docker=False)

    spans = [c for c in result.children if isinstance(c, html.Span)]
    ids = [s.id for s in spans]
    assert ids == [
        {"type": "reveal-exe", "path": "C:\\a.exe", "idx": 0},
        {"type": "reveal-exe", "path": "C:\\b.exe", "idx": 1},
    ]


def test_for_click_renders_exe_tag_as_plain_text_in_docker() -> None:
    """In Docker, '<exe full=...>' markup renders as plain text, not a clickable span."""
    full_path = r"C:\Program Files\WindowsApps\...\MicrosoftStartFeedProvider.exe"
    detail = f'Executable:  <exe full="{full_path}">C:\\...\\Feed.exe</exe>'
    view = {"details": {"0": detail}}

    result = _builder().for_click(_click_data(), view, is_docker=True)

    children = result.children
    assert not any(isinstance(c, html.Span) for c in children)
    assert "C:\\...\\Feed.exe" in children
    assert not any(isinstance(c, str) and "<exe" in c for c in children)
