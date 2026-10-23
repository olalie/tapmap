from __future__ import annotations

from datetime import date
from typing import Any

from dash import html

from ..state.insights import EntryHistory, country_name
from .formatting import country_flag

_SECTIONS = (
    ("[APPS]", "applications"),
    ("[PROVIDERS]", "providers"),
    ("[COUNTRIES]", "countries"),
    ("[PORTS]", "ports"),
)

_CATEGORY_LABELS = {
    "applications": "Application",
    "providers": "Network operator",
    "countries": "Country",
    "ports": "Port",
}


def render_insights_panel(
    data: dict[str, Any] | None,
    selected_country: str | None = None,
) -> list[Any]:
    """Render insights panel content from data."""
    if not isinstance(data, dict):
        return []

    top = data.get("top") or {}

    def build_row(item: dict[str, Any], category: str) -> Any:
        """Build one panel row; rows with a string value are clickable entries."""
        value = item.get("value")
        name = item.get("name") or value or ""

        is_country = category == "countries"
        flag = country_flag(value) if is_country else ""

        header = html.Div(
            [
                html.Span(flag, className="insights-flag"),
                html.Span(name, className="insights-country"),
            ],
            className="insights-row-header",
        )

        if not isinstance(value, str):
            return html.Div(header, className="insights-row")

        row_class = "insights-row clickable"
        if is_country and value == selected_country:
            row_class += " selected"

        return html.Div(
            header,
            className=row_class,
            id={
                "type": "insights-entry",
                "category": category,
                "value": value,
            },
            n_clicks=0,
        )

    def subtitle(text: str, items: list[Any]) -> Any:
        """Build a section subtitle, dimmed when the section is empty."""
        cls = "insights-subtitle" if items else "insights-subtitle dimmed"
        return html.Div(text, className=cls)

    sections = []
    for label, category in _SECTIONS:
        items = top.get(category) or []
        sections.append(
            html.Div(
                [
                    subtitle(label, items),
                    html.Div(
                        [build_row(i, category) for i in items],
                        className="insights-list",
                    ),
                ]
            )
        )

    return [html.Div("Top 5+", className="insights-title"), *sections]


def render_insights_entry_detail(
    category: str,
    value: str,
    history: EntryHistory | None,
    today_day: int,
) -> list[Any]:
    """Build modal content for one Insights entry's 30-day history.

    history: None renders an unavailable message.
    today_day: ordinal of the current day.
    """
    is_country = category == "countries"
    title = f"{country_flag(value)} {country_name(value)}" if is_country else value

    header = [
        html.H1(title, className="mx-h1"),
        html.P(_CATEGORY_LABELS.get(category, category), className="modal-subtitle"),
    ]

    if history is None:
        return [*header, html.Pre("(this entry is no longer available)")]

    strip = html.Div(
        [
            html.Span(
                "■" if active else "□",
                className="rpt-day--on" if active else "rpt-day--off",
            )
            for active in history["days"]
        ],
        className="rpt-day-strip",
    )
    window_start_day = today_day - (len(history["days"]) - 1)
    labeled_strip = html.Div(
        [
            html.Span(_format_short_day(window_start_day)),
            strip,
            html.Span(_format_short_day(today_day)),
        ],
        style={"display": "flex", "alignItems": "center", "gap": "8px"},
    )

    return [
        *header,
        _detail_table(
            [
                ("Last seen", _format_day(history["last_seen_day"], today_day)),
                (
                    "Earliest recorded (last 30 days)",
                    date.fromordinal(history["first_seen_day"]).isoformat(),
                ),
                ("Active days", f"{history['active_days']} of the last 30 days"),
                ("Activity", labeled_strip),
            ]
        ),
        html.P(
            "Each square shows one day, with today on the right. "
            "Filled squares mark recorded activity.",
            className="modal-subtitle",
        ),
    ]


def _format_day(day: int, today_day: int) -> str:
    """Format a day ordinal as Today, Yesterday, or YYYY-MM-DD."""
    if day == today_day:
        return "Today"
    if day == today_day - 1:
        return "Yesterday"
    return date.fromordinal(day).isoformat()


def _format_short_day(day: int) -> str:
    """Format a day ordinal as an abbreviated month and day, e.g. Sep 24."""
    d = date.fromordinal(day)
    return f"{d:%b} {d.day}"


def _detail_table(rows: list[tuple[str, Any]]) -> html.Table:
    """Build a two-column key/value table."""
    body = [html.Tr([html.Td(key), html.Td(value)]) for key, value in rows]
    colgroup = html.Colgroup([html.Col(style={"width": "35%"}), html.Col(style={"width": "65%"})])
    return html.Table(className="mx-table mx-kv", children=[colgroup, html.Tbody(body)])
