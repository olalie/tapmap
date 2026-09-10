"""Test about_view's rendering of runtime, notification, and CLI information."""

from __future__ import annotations

from typing import Any

from dash import html

from tapmap.ui.about_view import render_about


def _runtime_info(**overrides: Any) -> dict[str, Any]:
    """Return a minimal runtime_info dict as _build_runtime_info() would supply it."""
    info: dict[str, Any] = {
        "poll_interval_ms": 5000,
        "coord_precision": 3,
        "zoom_near_km": 25.0,
        "geoinfo_enabled": False,
        "geo_provider": "none",
        "geo_database_date": "-",
        "myloc_mode": "OFF",
        "my_location": None,
        "public_ip_cached": None,
        "auto_geo_cached": {},
        "os": "Windows 11",
        "python": "3.12.0",
        "net_backend": "psutil",
        "net_backend_version": "7.2.2",
        "server_host": "127.0.0.1",
        "server_port": 8050,
        "launch_browser": True,
        "cache_retention_min": 0,
        "is_docker": False,
        "notification_learning_days": 7,
        "mqtt_configured": False,
        "mqtt_host": None,
        "mqtt_port": None,
        "mqtt_topic": None,
        "mqtt_tls": None,
        "dash_version": "4.1.0",
    }
    info.update(overrides)
    return info


def _render(**overrides: Any) -> list[Any]:
    """Render About with a minimal snapshot built from the given runtime_info overrides."""
    return render_about(
        app_name="TapMap",
        app_version="1.12.3",
        app_author="Ola Lie",
        snapshot={"runtime_info": _runtime_info(**overrides)},
    )


def _section_table(result: list[Any], heading: str) -> html.Table:
    """Return the kv_table immediately following the H2 with the given text."""
    idx = next(
        i
        for i, c in enumerate(result)
        if isinstance(c, html.H2) and c.children == heading
    )
    table = result[idx + 1]
    assert isinstance(table, html.Table)
    return table


def _kv_rows(table: html.Table) -> dict[str, str]:
    """Return {label: value} for every row of a kv_table."""
    tbody = next(c for c in table.children if isinstance(c, html.Tbody))
    rows: dict[str, str] = {}
    for tr in tbody.children:
        key_cell, value_cell = tr.children
        rows[key_cell.children] = value_cell.children.children
    return rows


def _command_line_text(result: list[Any]) -> str:
    """Return the text content of the Command line Pre block."""
    pre = next(c for c in result if isinstance(c, html.Pre))
    return pre.children


def test_notifications_section_shows_learning_period_and_unconfigured_mqtt() -> None:
    """Verify the unconfigured MQTT display."""
    result = _render(mqtt_configured=False)
    rows = _kv_rows(_section_table(result, "Notifications"))

    assert rows == {"Learning period": "7 days", "MQTT configured": "No"}


def test_notifications_section_shows_broker_topic_and_tls_when_configured() -> None:
    """Verify configured MQTT details."""
    result = _render(
        mqtt_configured=True,
        mqtt_host="broker.example.com",
        mqtt_port=8883,
        mqtt_topic="tapmap/events",
        mqtt_tls=True,
    )
    rows = _kv_rows(_section_table(result, "Notifications"))

    assert rows["MQTT configured"] == "Yes"
    assert rows["Broker"] == "broker.example.com:8883"
    assert rows["Topic"] == "tapmap/events"
    assert rows["TLS"] == "On"


def test_notifications_section_falls_back_when_learning_period_missing() -> None:
    """Verify the learning-period fallback."""
    result = _render(notification_learning_days=None)
    rows = _kv_rows(_section_table(result, "Notifications"))

    assert rows["Learning period"] == "-"


def test_runtime_section_shows_frontend_and_dash_version() -> None:
    """Verify displayed frontend information."""
    result = _render(dash_version="4.1.0")
    rows = _kv_rows(_section_table(result, "Runtime"))

    assert rows["Frontend"] == "Dash"
    assert rows["Frontend version"] == "4.1.0"


def test_runtime_section_docker_flag_comes_from_runtime_info() -> None:
    """Verify Docker status from runtime information."""
    result = _render(is_docker=True)
    rows = _kv_rows(_section_table(result, "Runtime"))

    assert rows["Docker"] == "Yes"


def test_command_line_block_includes_configure_mqtt() -> None:
    """Verify the MQTT configuration command."""
    text = _command_line_text(_render())

    assert "tapmap --configure-mqtt" in text
    assert "tapmap --help" in text
    assert "tapmap --version" in text
    assert "tapmap --no-browser" in text
