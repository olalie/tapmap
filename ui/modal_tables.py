from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from dash import html


@dataclass(frozen=True)
class ColumnSpec:
    """Describe one table column."""

    header: str
    width: str | None = None


def cell(text: str, *, title: str | None = None) -> html.Td:
    """Render a table cell with truncation and tooltip."""
    value = text or ""
    tooltip = title if title is not None else value
    tooltip = tooltip if tooltip else None
    return html.Td(
        html.Span(value, className="mx-cell-text", title=tooltip)
    )


def build_table(
    *,
    class_name: str,
    columns: Sequence[ColumnSpec],
    header_cells: Sequence[str],
    body_rows: Iterable[Any],
) -> html.Table:
    """Build a Dash HTML table with colgroup, thead and tbody."""
    colgroup = html.Colgroup(
        [
            html.Col(style={"width": col.width}) if col.width else html.Col()
            for col in columns
        ]
    )

    thead = html.Thead(
        html.Tr([html.Th(h) for h in header_cells])
    )

    tbody = html.Tbody(list(body_rows))

    return html.Table(
        className=class_name,
        children=[colgroup, thead, tbody],
    )

def kv_table(rows: Iterable[tuple[str, str]]) -> html.Table:
    """Build a two column key/value table with tooltips."""
    body: list[Any] = []
    for key, value in rows:
        v = "" if value is None else str(value)
        body.append(
            html.Tr(
                [
                    html.Td(key),
                    html.Td(html.Span(v, title=v if v else None)),
                ]
            )
        )

    colgroup = html.Colgroup(
        [
            html.Col(style={"width": "180px"}),
            html.Col(),
        ]
    )

    return html.Table(
        className="mx-table mx-info-table",
        children=[colgroup, html.Tbody(body)],
    )