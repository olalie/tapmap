"""Test ConnectionAnalyzer's mapped-PUBLIC classification and insights update."""

from __future__ import annotations

from typing import Any

from tapmap.state.connection_analyzer import ConnectionAnalyzer
from tapmap.state.connection_state import ConnectionState


def _cache_item(**overrides: Any) -> dict[str, Any]:
    """Return a minimal cache_items-shaped dict (as produced by Model.snapshot())."""
    item = {
        "ip": "8.8.8.8",
        "port": 443,
        "proto": "tcp",
        "service_scope": "PUBLIC",
        "lat": 37.4,
        "lon": -122.1,
        "city": "Mountain View",
        "country": "United States",
        "country_code": "US",
        "asn": 15169,
        "asn_org": "Google LLC",
        "process_name": None,
        "pid": None,
        "exe": None,
        "app_name": None,
        "app_creator": None,
        "app_verification_status": None,
        "app_signature_state": None,
        "app_signature_state_details": None,
    }
    item.update(overrides)
    return item


# --- classification: mapped PUBLIC vs. everything else ---


def test_analyze_merges_public_connection_with_coordinates() -> None:
    """A PUBLIC connection with valid lat/lon is classified as mapped and merged."""
    connection_state = ConnectionState()
    analyzer = ConnectionAnalyzer(connection_state, {})

    analyzer.analyze([_cache_item()])

    assert "8.8.8.8|443" in connection_state.cache


def test_analyze_excludes_public_connection_without_coordinates() -> None:
    """A PUBLIC connection missing lat/lon is not merged into ConnectionState."""
    connection_state = ConnectionState()
    analyzer = ConnectionAnalyzer(connection_state, {})

    analyzer.analyze([_cache_item(lat=None, lon=None)])

    assert connection_state.cache == {}


def test_analyze_excludes_non_public_scopes() -> None:
    """LAN, LOCAL, and UNKNOWN scoped connections are never merged into ConnectionState."""
    connection_state = ConnectionState()
    analyzer = ConnectionAnalyzer(connection_state, {})

    analyzer.analyze(
        [
            _cache_item(ip="192.168.1.1", service_scope="LAN"),
            _cache_item(ip="127.0.0.1", service_scope="LOCAL"),
            _cache_item(ip="10.0.0.1", service_scope="UNKNOWN"),
        ]
    )

    assert connection_state.cache == {}


# --- insights: updated from the full connection set, not just mapped ---


def test_analyze_feeds_full_cache_items_to_insights_not_just_mapped() -> None:
    """Insights are updated from every PUBLIC connection, including unmapped ones."""
    insights: dict[str, Any] = {}
    analyzer = ConnectionAnalyzer(ConnectionState(), insights)

    analyzer.analyze([_cache_item(lat=None, lon=None, country_code="NO")])

    assert "NO" in insights["countries"]


def test_analyze_excludes_non_public_connections_from_insights() -> None:
    """LAN/LOCAL/UNKNOWN connections do not contribute to Insights."""
    insights: dict[str, Any] = {}
    analyzer = ConnectionAnalyzer(ConnectionState(), insights)

    analyzer.analyze([_cache_item(ip="192.168.1.1", service_scope="LAN", country_code="NO")])

    assert insights.get("countries", {}) == {}


def test_analyze_returns_process_insights_result() -> None:
    """analyze() returns the same {new, top} shape process_insights() produces."""
    analyzer = ConnectionAnalyzer(ConnectionState(), {})

    result = analyzer.analyze([_cache_item()])

    assert set(result.keys()) == {"new", "top"}
    assert result["new"]["countries"][0]["value"] == "US"
