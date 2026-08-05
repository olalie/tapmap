from __future__ import annotations

from typing import Any

from dash import html

from .formatting import country_flag


def render_insights_panel(
    data: dict[str, Any] | None,
    selected_country: str | None = None,
) -> list[Any]:
    """Render insights panel content from data."""
    if not isinstance(data, dict):
        return []

    new = data.get("new") or {}
    top = data.get("top") or {}

    def build_row(item: dict[str, Any], category: str, section: str) -> Any:
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

        if is_country and isinstance(value, str):
            row_class = "insights-row clickable"

            if value == selected_country:
                row_class += " selected"

            return html.Div(
                header,
                className=row_class,
                id={
                    "type": "insights-country",
                    "country_code": value,
                    "section": section,
                },
                n_clicks=0,
            )

        return html.Div(header, className="insights-row")

    def subtitle(text: str, items: list[Any]) -> Any:
        cls = "insights-subtitle" if items else "insights-subtitle dimmed"
        return html.Div(text, className=cls)

    return [
        html.Div("Today", className="insights-title"),

        html.Div(
            [
                subtitle("[NEW APPS]", new.get("applications") or []),
                html.Div(
                    [
                        build_row(i, "applications", "today")
                        for i in (new.get("applications") or [])
                    ],
                    className="insights-list",
                ),
            ]
        ),

        html.Div(
            [
                subtitle("[NEW PROVIDERS]", new.get("providers") or []),
                html.Div(
                    [
                        build_row(i, "providers", "today")
                        for i in (new.get("providers") or [])
                    ],
                    className="insights-list",
                ),
            ]
        ),

        html.Div(
            [
                subtitle("[NEW COUNTRIES]", new.get("countries") or []),
                html.Div(
                    [
                        build_row(i, "countries", "today")
                        for i in (new.get("countries") or [])
                    ],
                    className="insights-list",
                ),
            ]
        ),

        html.Div(
            [
                subtitle("[NEW PORTS]", new.get("ports") or []),
                html.Div(
                    [
                        build_row(i, "ports", "today")
                        for i in (new.get("ports") or [])
                    ],
                    className="insights-list",
                ),
            ]
        ),

        html.Div("Top 5+", className="insights-title"),

        html.Div(
            [
                subtitle("[APPS]", top.get("applications") or []),
                html.Div(
                    [
                        build_row(i, "applications", "top")
                        for i in (top.get("applications") or [])
                    ],
                    className="insights-list",
                ),
            ]
        ),

        html.Div(
            [
                subtitle("[PROVIDERS]", top.get("providers") or []),
                html.Div(
                    [
                        build_row(i, "providers", "top")
                        for i in (top.get("providers") or [])
                    ],
                    className="insights-list",
                ),
            ]
        ),

        html.Div(
            [
                subtitle("[COUNTRIES]", top.get("countries") or []),
                html.Div(
                    [
                        build_row(i, "countries", "top")
                        for i in (top.get("countries") or [])
                    ],
                    className="insights-list",
                ),
            ]
        ),

        html.Div(
            [
                subtitle("[PORTS]", top.get("ports") or []),
                html.Div(
                    [
                        build_row(i, "ports", "top")
                        for i in (top.get("ports") or [])
                    ],
                    className="insights-list",
                ),
            ]
        ),
    ]
