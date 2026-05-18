"""Daily Activity Report view rendering for the TapMap UI."""

from __future__ import annotations

from typing import Any

from dash import html


def render_daily_activity_report() -> list[Any]:
    """Render placeholder content for the Daily Activity Report modal."""
    return [
        html.H1("Daily Activity Report"),
        html.P("Daily activity report is not yet available.", className="mx-note"),
    ]
