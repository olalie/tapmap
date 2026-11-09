"""Test ConnectionAnalyzer's PUBLIC classification, insights update, and significance wiring."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pytest

from tapmap.state.connection_analyzer import ConnectionAnalyzer
from tapmap.state.connection_state import ConnectionState
from tapmap.state.insights_state import InsightsState
from tapmap.state.significance import SignificanceHistory
from tapmap.state.significant_connections import SignificantConnections
from tapmap.state.unmapped_state import UnmappedState


def _empty_history() -> SignificanceHistory:
    """Return a fresh SignificanceHistory derived from empty Insights."""
    return SignificanceHistory.from_insights_state(
        InsightsState(
            version=2,
            insights={"countries": {}, "providers": {}, "ports": {}, "applications": {}},
            verification_failed={},
        )
    )


def _insights_state(
    insights: dict[str, Any] | None = None, *, learning_completed_day: int | None = None
) -> InsightsState:
    """Return an InsightsState wrapping insights by reference."""
    return InsightsState(
        version=2,
        insights=insights if insights is not None else {},
        verification_failed={},
        notification_learning_completed_day=learning_completed_day,
    )


def _connection(**overrides: Any) -> dict[str, Any]:
    """Return a minimal connection dict (as produced by Model.snapshot())."""
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


def _analyzer(
    connection_state: ConnectionState | None = None,
    unmapped_state: UnmappedState | None = None,
    insights: dict[str, Any] | None = None,
) -> ConnectionAnalyzer:
    """Build a ConnectionAnalyzer with fresh, empty significance collaborators."""
    return ConnectionAnalyzer(
        connection_state if connection_state is not None else ConnectionState(),
        unmapped_state if unmapped_state is not None else UnmappedState(),
        _insights_state(insights),
        SignificantConnections([]),
        SignificanceHistory.from_insights_state(
            InsightsState(
                version=2,
                insights={"countries": {}, "providers": {}, "ports": {}, "applications": {}},
                verification_failed={},
            )
        ),
    )


# --- classification: mapped PUBLIC vs. everything else ---


def test_analyze_merges_public_connection_with_coordinates() -> None:
    """A PUBLIC connection with valid lat/lon is classified as mapped and merged."""
    connection_state = ConnectionState()
    analyzer = _analyzer(connection_state)

    analyzer.analyze([_connection()])

    assert "8.8.8.8|443" in connection_state.cache


def test_analyze_excludes_public_connection_without_coordinates() -> None:
    """A PUBLIC connection missing lat/lon is not merged into ConnectionState."""
    connection_state = ConnectionState()
    analyzer = _analyzer(connection_state)

    analyzer.analyze([_connection(lat=None, lon=None)])

    assert connection_state.cache == {}


def test_analyze_excludes_non_public_scopes() -> None:
    """LAN, LOCAL, and UNKNOWN scoped connections are never merged into ConnectionState."""
    connection_state = ConnectionState()
    analyzer = _analyzer(connection_state)

    analyzer.analyze(
        [
            _connection(ip="192.168.1.1", service_scope="LAN"),
            _connection(ip="127.0.0.1", service_scope="LOCAL"),
            _connection(ip="10.0.0.1", service_scope="UNKNOWN"),
        ]
    )

    assert connection_state.cache == {}


# --- insights: updated only from mapped PUBLIC connections ---


def test_analyze_feeds_mapped_public_connections_to_insights() -> None:
    """Insights are updated from mapped PUBLIC connections (valid lat/lon)."""
    insights: dict[str, Any] = {}
    analyzer = _analyzer(insights=insights)

    analyzer.analyze([_connection(country_code="NO")])

    assert "NO" in insights["countries"]


def test_analyze_excludes_unmapped_public_connections_from_insights() -> None:
    """A PUBLIC connection without usable GeoIP does not contribute to Insights."""
    insights: dict[str, Any] = {}
    analyzer = _analyzer(insights=insights)

    analyzer.analyze([_connection(lat=None, lon=None, country_code="NO")])

    assert insights.get("countries", {}) == {}


def test_analyze_excludes_non_public_connections_from_insights() -> None:
    """LAN/LOCAL/UNKNOWN connections do not contribute to Insights."""
    insights: dict[str, Any] = {}
    analyzer = _analyzer(insights=insights)

    analyzer.analyze([_connection(ip="192.168.1.1", service_scope="LAN", country_code="NO")])

    assert insights.get("countries", {}) == {}


def test_analyze_returns_process_insights_result() -> None:
    """analyze() returns the same {top} shape process_insights() produces."""
    analyzer = _analyzer()

    result, _ = analyzer.analyze([_connection()])

    assert set(result.keys()) == {"top"}
    assert result["top"]["countries"][0]["value"] == "US"


# --- significant connections wiring ---


def test_analyze_records_significant_event_for_novel_public_connection() -> None:
    """A PUBLIC connection with a never-seen country produces one Significant Connection event."""
    significant_connections = SignificantConnections([])
    analyzer = ConnectionAnalyzer(
        ConnectionState(),
        UnmappedState(),
        _insights_state(),
        significant_connections,
        SignificanceHistory.from_insights_state(
            InsightsState(
                version=2,
                insights={"countries": {}, "providers": {}, "ports": {}, "applications": {}},
                verification_failed={},
            )
        ),
    )

    analyzer.analyze([_connection(country_code="US")])

    assert len(significant_connections.items) == 1
    event = significant_connections.items[0]
    assert "new_country" in event["reasons"]
    assert event["ip"] == "8.8.8.8"


def test_analyze_does_not_evaluate_significance_for_non_public_connections() -> None:
    """LAN/LOCAL/UNKNOWN connections are filtered out before significance is ever checked."""
    significant_connections = SignificantConnections([])
    analyzer = ConnectionAnalyzer(
        ConnectionState(),
        UnmappedState(),
        _insights_state(),
        significant_connections,
        SignificanceHistory.from_insights_state(
            InsightsState(
                version=2,
                insights={"countries": {}, "providers": {}, "ports": {}, "applications": {}},
                verification_failed={},
            )
        ),
    )

    analyzer.analyze(
        [_connection(ip="192.168.1.1", service_scope="LAN", country_code="NO", port=9999)]
    )

    assert significant_connections.items == []


def test_analyze_does_not_repeat_significant_event_for_same_snapshot_repeat() -> None:
    """Two consecutive analyze() calls with the same connection produce only one event."""
    significant_connections = SignificantConnections([])
    history = SignificanceHistory.from_insights_state(
        InsightsState(
            version=2,
            insights={"countries": {}, "providers": {}, "ports": {}, "applications": {}},
            verification_failed={},
        )
    )
    analyzer = ConnectionAnalyzer(
        ConnectionState(), UnmappedState(), _insights_state(), significant_connections, history
    )

    analyzer.analyze([_connection(country_code="US")])
    analyzer.analyze([_connection(country_code="US")])

    assert len(significant_connections.items) == 1


# --- mapped/unmapped routing ---


def test_analyze_routes_public_without_geo_to_unmapped_state() -> None:
    """A PUBLIC connection missing lat/lon is merged into UnmappedState, not ConnectionState."""
    connection_state = ConnectionState()
    unmapped_state = UnmappedState()
    analyzer = _analyzer(connection_state, unmapped_state)

    analyzer.analyze([_connection(lat=None, lon=None)])

    assert connection_state.cache == {}
    assert "8.8.8.8|443" in unmapped_state.cache


def test_analyze_routes_public_with_geo_to_connection_state_only() -> None:
    """A PUBLIC connection with valid lat/lon is merged into ConnectionState, not UnmappedState."""
    connection_state = ConnectionState()
    unmapped_state = UnmappedState()
    analyzer = _analyzer(connection_state, unmapped_state)

    analyzer.analyze([_connection()])

    assert "8.8.8.8|443" in connection_state.cache
    assert unmapped_state.cache == {}


def test_verification_backfill_does_not_suppress_a_later_verification_failed_event() -> None:
    """Verify that backfill does not suppress a later verification failure."""
    significant_connections = SignificantConnections([])
    history = SignificanceHistory.from_insights_state(
        InsightsState(
            version=2,
            insights={"countries": {}, "providers": {}, "ports": {}, "applications": {}},
            verification_failed={},
        )
    )
    analyzer = ConnectionAnalyzer(
        ConnectionState(), UnmappedState(), _insights_state(), significant_connections, history
    )

    analyzer.analyze(
        [_connection(exe="/opt/app.exe", app_name="App", app_verification_status=None)]
    )
    assert len(significant_connections.items) == 1
    first_reasons = significant_connections.items[0]["reasons"]
    assert "new_app" in first_reasons
    assert "verification_failed" not in first_reasons

    significant_connections.refresh_resolved_applications(
        {
            "/opt/app.exe": {
                "app_creator": "Vendor Inc.",
                "app_verification_status": "failed",
                "app_signature_state": "Unsigned",
                "app_signature_state_details": None,
            }
        }
    )
    assert significant_connections.items[0]["app_verification_status"] == "failed"
    assert significant_connections.items[0]["reasons"] == first_reasons

    analyzer.analyze(
        [_connection(exe="/opt/app.exe", app_name="App", app_verification_status="failed")]
    )

    assert len(significant_connections.items) == 2
    assert significant_connections.items[0]["reasons"] == first_reasons
    assert significant_connections.items[1]["reasons"] == ["verification_failed"]
    assert significant_connections.items[1]["app_verification_status"] == "failed"


# --- notifiable events ---


def test_no_notifiable_events_during_learning_period() -> None:
    """Record the event but return no notifiable events during learning."""
    significant_connections = SignificantConnections([])
    analyzer = ConnectionAnalyzer(
        ConnectionState(),
        UnmappedState(),
        _insights_state(),
        significant_connections,
        _empty_history(),
        notification_learning_days=7,
    )

    _, notifiable_events = analyzer.analyze([_connection(country_code="US")])

    assert len(significant_connections.items) == 1
    assert notifiable_events == []


def test_notifiable_events_after_learning_period_is_over() -> None:
    """Return the recorded event as notifiable once learning has completed."""
    significant_connections = SignificantConnections([])
    # 7 distinct active days ending on day 1.
    insights: dict[str, Any] = {
        "countries": {"NO": {"l": 1, "m": (1 << 7) - 1}},
    }
    analyzer = ConnectionAnalyzer(
        ConnectionState(),
        UnmappedState(),
        _insights_state(insights),
        significant_connections,
        _empty_history(),
        notification_learning_days=7,
    )

    _, notifiable_events = analyzer.analyze([_connection(country_code="US")])

    assert len(significant_connections.items) == 1
    assert notifiable_events == [significant_connections.items[0]]


def test_current_poll_does_not_count_toward_its_own_eligibility() -> None:
    """Return no notifiable events when only the current poll would reach the threshold."""
    significant_connections = SignificantConnections([])
    # 6 active days already recorded; today's observation would be the 7th,
    # but only after process_insights() runs at the end of analyze().
    insights: dict[str, Any] = {
        "countries": {"NO": {"l": 1, "m": (1 << 6) - 1}},
    }
    analyzer = ConnectionAnalyzer(
        ConnectionState(),
        UnmappedState(),
        _insights_state(insights),
        significant_connections,
        _empty_history(),
        notification_learning_days=7,
    )

    _, notifiable_events = analyzer.analyze([_connection(country_code="US")])

    assert len(significant_connections.items) == 1
    assert notifiable_events == []


def test_recorded_learning_completion_survives_short_window_and_higher_threshold() -> None:
    """Return notifiable events with no active Insights days and a raised threshold."""
    significant_connections = SignificantConnections([])
    analyzer = ConnectionAnalyzer(
        ConnectionState(),
        UnmappedState(),
        _insights_state(learning_completed_day=739000),
        significant_connections,
        _empty_history(),
        notification_learning_days=14,
    )

    _, notifiable_events = analyzer.analyze([_connection(country_code="US")])

    assert notifiable_events == [significant_connections.items[0]]


def test_learning_completion_is_recorded_and_logged_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Record today as the completion day and log it once across polls."""
    insights_state = _insights_state({"countries": {"NO": {"l": 1, "m": (1 << 7) - 1}}})
    analyzer = ConnectionAnalyzer(
        ConnectionState(),
        UnmappedState(),
        insights_state,
        SignificantConnections([]),
        _empty_history(),
        notification_learning_days=7,
    )

    with caplog.at_level(logging.INFO, logger="tapmap.state.connection_analyzer"):
        analyzer.analyze([_connection(country_code="US")])
        analyzer.analyze([_connection(country_code="SE")])

    assert insights_state.notification_learning_completed_day == date.today().toordinal()
    assert caplog.text.count("Notification learning period completed") == 1


def test_zero_learning_days_notifies_without_recording_completion() -> None:
    """Return notifiable events for 0 learning days and leave completion unrecorded."""
    significant_connections = SignificantConnections([])
    insights_state = _insights_state()
    analyzer = ConnectionAnalyzer(
        ConnectionState(),
        UnmappedState(),
        insights_state,
        significant_connections,
        _empty_history(),
        notification_learning_days=0,
    )

    _, notifiable_events = analyzer.analyze([_connection(country_code="US")])

    assert notifiable_events == [significant_connections.items[0]]
    assert insights_state.notification_learning_completed_day is None


def test_learning_suppression_is_logged_once(caplog: pytest.LogCaptureFixture) -> None:
    """Log suppressed notifications once across polls with new Significant Connections."""
    analyzer = ConnectionAnalyzer(
        ConnectionState(),
        UnmappedState(),
        _insights_state(),
        SignificantConnections([]),
        _empty_history(),
        notification_learning_days=7,
    )

    with caplog.at_level(logging.INFO, logger="tapmap.state.connection_analyzer"):
        analyzer.analyze([_connection(country_code="US")])
        analyzer.analyze([_connection(country_code="SE")])

    assert caplog.text.count("notifications start after 7 active Insights days") == 1
