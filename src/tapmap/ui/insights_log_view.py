"""Insights log viewer rendering for the TapMap UI."""

from __future__ import annotations

from typing import Any

from dash import html


def render_insights_log(text: str) -> list[Any]:
    """Render the insights log content as a terminal-style modal screen."""
    return [
        html.Div(
            className="insights-log-body",
            children=[
                html.Button(
                    "← Daily Activity Report",
                    id="btn_log_back",
                    n_clicks=0,
                    className="mx-btn mx-btn--nowrap",
                    type="button",
                ),
                html.H1("Insights Log"),
                html.Div(
                    className="insights-log-pre-wrapper",
                    children=[
                        html.Pre(
                            text if text else "No log data available.",
                            className="insights-log-pre",
                        ),
                    ],
                ),
            ],
        )
    ]
