"""Test TapMap's coordination of ConnectionState and UnmappedState."""

from __future__ import annotations

import hashlib
import logging
import threading
from collections.abc import Iterator
from contextvars import copy_context
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import dash
import pytest
from dash import html
from dash._callback_context import context_value
from dash._utils import AttributeDict

from tapmap import app as app_module
from tapmap.app import APP_META, TapMap
from tapmap.lifecycle import start_poller_thread
from tapmap.model.appinfo import ApplicationMetadata, VerificationStatus
from tapmap.mqtt_config import MqttConfig, mqtt_config_path, save_mqtt_config
from tapmap.runtime import RuntimeContext
from tapmap.significant_connections_persistence import load_significant_connections
from tapmap.state.connection_state import ConnectionState
from tapmap.state.insights_state import CURRENT_SCHEMA_VERSION, InsightsState
from tapmap.state.poll import ACTION_ZOOM_CONNECTIONS
from tapmap.state.significant_connections import SignificantConnections
from tapmap.state.status_cache import StatusCache
from tapmap.state.unmapped_state import UnmappedState
from tapmap.ui.service_point_view import ServicePointViewBuilder


def _runtime_ctx(tmp_path: Path) -> RuntimeContext:
    """Build a minimal runtime context for app construction tests."""
    return RuntimeContext(
        meta=APP_META,
        app_data_dir=tmp_path,
        run_dir=tmp_path,
        is_frozen=False,
        net_backend="psutil",
        net_backend_version="test",
        server_host="127.0.0.1",
        server_port=8050,
        launch_browser=True,
        cache_retention_min=0,
        is_docker=False,
        location_override=None,
        security_extensions_dir=tmp_path,
        tray_icon_path=tmp_path / "tapmap.ico",
        notification_learning_days=7,
    )


def _bare_app() -> TapMap:
    """Return a TapMap instance with only the attributes needed for method-level tests."""
    app = object.__new__(TapMap)
    app.connection_state = ConnectionState()
    app.unmapped_state = UnmappedState()
    app.significant_connections = SignificantConnections([])
    app.view_builder = ServicePointViewBuilder(coord_precision=3, is_docker=False)
    app.model = SimpleNamespace(appinfo=MagicMock())
    app.MIN_FLASH_S = TapMap.MIN_FLASH_S
    return app


def _mapped_candidate(**overrides: object) -> dict[str, object]:
    """Return a minimal mapped PUBLIC candidate for ConnectionState.merge()."""
    candidate = {
        "ip": "8.8.8.8",
        "port": 443,
        "proto": "tcp",
        "process_name": None,
        "pid": None,
        "exe": "/opt/app.exe",
        "lon": 37.4,
        "lat": -122.1,
        "city": "Mountain View",
        "country": "United States",
        "country_code": "US",
        "asn": 15169,
        "asn_org": "Google LLC",
        "app_name": None,
        "app_creator": None,
        "app_verification_status": None,
        "app_signature_state": None,
        "app_signature_state_details": None,
    }
    candidate.update(overrides)
    return candidate


def _unmapped_candidate(**overrides: object) -> dict[str, object]:
    """Return a minimal unmapped PUBLIC candidate for UnmappedState.merge()."""
    candidate = {
        "ip": "203.0.113.7",
        "port": 8443,
        "proto": "tcp",
        "service": "https",
        "process_name": None,
        "pid": None,
        "exe": "/opt/app.exe",
        "app_name": None,
        "app_creator": None,
        "app_verification_status": None,
        "app_signature_state": None,
        "app_signature_state_details": None,
    }
    candidate.update(overrides)
    return candidate


# --- Clear cache ---


def test_handle_clear_cache_clears_both_connection_and_unmapped_state() -> None:
    """Clear cache empties both ConnectionState and UnmappedState, not just the mapped one."""
    app = _bare_app()
    app.connection_state.merge([_mapped_candidate()])
    app.unmapped_state.merge([_unmapped_candidate()])

    app._handle_clear_cache(StatusCache(), False)

    assert app.connection_state.cache == {}
    assert app.unmapped_state.cache == {}


# --- Deferred AppInfo verification ---


def _pending_significant_event(**overrides: object) -> dict[str, object]:
    """Return a minimal persisted Significant Connection event awaiting verification."""
    event = {
        "timestamp": "2026-08-23T18:42:16.013313",
        "reasons": ["new_app"],
        "pid": 4821,
        "proto": "tcp",
        "ip": "8.8.8.8",
        "port": 443,
        "service": "https",
        "lat": 37.4,
        "lon": -122.1,
        "process_name": "firefox.exe",
        "exe": "/opt/app.exe",
        "city": "Mountain View",
        "country": "United States",
        "country_code": "US",
        "asn": 15169,
        "asn_org": "Google LLC",
        "app_name": "Firefox",
        "app_creator": None,
        "app_verification_status": None,
        "app_signature_state": None,
        "app_signature_state_details": None,
    }
    event.update(overrides)
    return event


def test_refresh_pending_app_verifications_updates_all_three_states() -> None:
    """Verify that a resolved executable backfills all three states."""
    app = _bare_app()
    app.connection_state.merge([_mapped_candidate(exe="/opt/app.exe", app_name="Firefox")])
    app.unmapped_state.merge([_unmapped_candidate(exe="/opt/app.exe", app_name="Firefox")])
    app.significant_connections.add(_pending_significant_event())

    app.model.appinfo.resolved_for.return_value = {
        "/opt/app.exe": ApplicationMetadata(
            name="Firefox",
            creator="Mozilla Corporation",
            verification_status=VerificationStatus.VERIFIED,
            signature_state="SignedAndTrusted",
            signature_state_details=None,
        )
    }

    app._refresh_pending_app_verifications()

    mapped_app = app.connection_state.cache["8.8.8.8|443"]["applications"]["/opt/app.exe"]
    unmapped_app = app.unmapped_state.cache["203.0.113.7|8443"]["applications"]["/opt/app.exe"]
    significant_event = app.significant_connections.items[0]

    assert mapped_app["app_verification_status"] == "verified"
    assert mapped_app["app_creator"] == "Mozilla Corporation"
    assert unmapped_app["app_verification_status"] == "verified"
    assert unmapped_app["app_creator"] == "Mozilla Corporation"
    assert significant_event["app_verification_status"] == "verified"
    assert significant_event["app_creator"] == "Mozilla Corporation"
    assert significant_event["reasons"] == ["new_app"]


def test_refresh_pending_app_verifications_queries_significant_connections_only_pending_exe(
) -> None:
    """Verify backfill after an executable has left the live connection states."""
    app = _bare_app()
    app.significant_connections.add(_pending_significant_event(exe="/opt/gone.exe"))

    app.model.appinfo.resolved_for.return_value = {
        "/opt/gone.exe": ApplicationMetadata(
            name="Firefox",
            creator="Mozilla Corporation",
            verification_status=VerificationStatus.FAILED,
            signature_state="Unsigned",
            signature_state_details=None,
        )
    }

    app._refresh_pending_app_verifications()

    app.model.appinfo.resolved_for.assert_called_once_with({"/opt/gone.exe"})
    assert app.significant_connections.items[0]["app_verification_status"] == "failed"


def test_refresh_pending_app_verifications_persists_the_corrected_significant_event(
    tmp_path: Path,
) -> None:
    """A Significant Connection backfilled in memory is saved to disk, not only in memory."""
    app = TapMap(_runtime_ctx(tmp_path))
    try:
        app.significant_connections.add(_pending_significant_event())

        resolved_metadata = ApplicationMetadata(
            name="Firefox",
            creator="Mozilla Corporation",
            verification_status=VerificationStatus.VERIFIED,
            signature_state="SignedAndTrusted",
            signature_state_details=None,
        )
        app.model.appinfo.resolved_for = lambda _paths: {"/opt/app.exe": resolved_metadata}

        app._refresh_pending_app_verifications()
        app._save_history()

        persisted = load_significant_connections(app.significant_connections_path)
        assert len(persisted) == 1
        assert persisted[0]["app_verification_status"] == "verified"
        assert persisted[0]["app_creator"] == "Mozilla Corporation"
        assert persisted[0]["reasons"] == ["new_app"]
    finally:
        app.close()


class _RecordingChannel:
    """Record events sent to the channel."""

    def __init__(self) -> None:
        """Start with no received events."""
        self.received: list[dict[str, Any]] = []

    def send(self, event: dict[str, Any]) -> None:
        """Record event."""
        self.received.append(event)


def test_normal_poll_dispatches_notifiable_events_to_channels(tmp_path: Path) -> None:
    """Send each notifiable Significant Connection from a poll to every channel."""
    app = TapMap(replace(_runtime_ctx(tmp_path), notification_learning_days=0))
    try:
        channel = _RecordingChannel()
        app.notification_channels = [channel]
        app.model.snapshot = lambda: {
            "connections": [_mapped_candidate(service_scope="PUBLIC", app_name="Firefox")]
        }

        app.poll_once()

        assert channel.received == app.significant_connections.items
        assert len(channel.received) == 1
    finally:
        app.close()


@pytest.mark.parametrize("failed_snapshot", [None, {"error": True}])
def test_failed_snapshot_does_not_save_history(tmp_path: Path, failed_snapshot: Any) -> None:
    """Skip saving history after a poll whose snapshot failed."""
    app = TapMap(_runtime_ctx(tmp_path))
    try:
        app.model.snapshot = lambda: failed_snapshot

        app.poll_once()

        assert not app.insights_path.exists()
        assert not app.significant_connections_path.exists()
    finally:
        app.close()


def test_close_waits_for_running_snapshot_before_closing_geoinfo(tmp_path: Path) -> None:
    """Close the GeoInfo readers only after a running snapshot has finished."""
    app = TapMap(_runtime_ctx(tmp_path))
    snapshot_started = threading.Event()
    release_snapshot = threading.Event()
    order: list[str] = []

    def _blocking_snapshot() -> dict[str, Any]:
        """Signal that the snapshot started, then return once released."""
        snapshot_started.set()
        release_snapshot.wait(timeout=5)
        order.append("snapshot")
        return {"connections": []}

    def _record_close() -> None:
        """Record the close."""
        order.append("close")

    app.model.snapshot = _blocking_snapshot
    app.model.geoinfo.close = _record_close
    poll = threading.Thread(target=app.poll_once)
    close = threading.Thread(target=app.close)
    try:
        poll.start()
        assert snapshot_started.wait(timeout=5)
        close.start()
        close.join(timeout=0.2)
        assert close.is_alive()

        release_snapshot.set()
        poll.join(timeout=5)
        close.join(timeout=5)
        assert order == ["snapshot", "close"]
    finally:
        release_snapshot.set()
        close.join(timeout=5)


_POLL_OUTPUTS = {
    ("model_snapshot", "data"),
    ("status_cache", "data"),
    ("ui_view", "data"),
    ("status_flash", "data"),
    ("insights_cache", "data"),
}


def test_clear_cache_waits_for_poll_applying_its_snapshot(tmp_path: Path) -> None:
    """Run Clear cache only after a poll that is updating shared state has finished."""
    app = TapMap(_runtime_ctx(tmp_path))
    analysis_started = threading.Event()
    release_analysis = threading.Event()
    try:
        app.model.snapshot = lambda: {"connections": [_mapped_candidate(service_scope="PUBLIC")]}
        real_analyze = app.connection_analyzer.analyze

        def _blocking_analyze(items: list[dict[str, Any]]) -> Any:
            """Signal that analysis started, then analyze items once released."""
            analysis_started.set()
            release_analysis.wait(timeout=5)
            return real_analyze(items)

        app.connection_analyzer.analyze = _blocking_analyze
        spec = _callback_by_outputs_and_input(app, _POLL_OUTPUTS, ("menu_clear_cache", "n_clicks"))
        triggered = {"prop_id": "menu_clear_cache.n_clicks", "value": 1}
        poll = threading.Thread(target=app.poll_once)
        clear = threading.Thread(
            target=_run_callback, args=(spec, triggered, 0, None, 1, False, None, None)
        )

        poll.start()
        assert analysis_started.wait(timeout=5)
        clear.start()
        clear.join(timeout=0.2)
        assert clear.is_alive()

        release_analysis.set()
        poll.join(timeout=5)
        clear.join(timeout=5)
        assert not clear.is_alive()
        assert app.connection_state.cache == {}
    finally:
        release_analysis.set()
        app.close()


def test_geodb_reload_waits_for_running_snapshot(tmp_path: Path) -> None:
    """Reload GeoInfo readers only after a running snapshot has finished."""
    app = TapMap(_runtime_ctx(tmp_path))
    snapshot_started = threading.Event()
    release_snapshot = threading.Event()
    order: list[str] = []
    try:

        def _blocking_snapshot() -> dict[str, Any]:
            """Signal that the snapshot started, then return once released."""
            snapshot_started.set()
            release_snapshot.wait(timeout=5)
            order.append("snapshot")
            return {"connections": []}

        def _record_reload() -> bool:
            """Record the reload."""
            order.append("reload")
            return True

        app.model.snapshot = _blocking_snapshot
        app.model.geoinfo.reload = _record_reload
        poll = threading.Thread(target=app.poll_once)
        reload = threading.Thread(target=app._reload_geodb_runtime)

        poll.start()
        assert snapshot_started.wait(timeout=5)
        reload.start()
        reload.join(timeout=0.2)
        assert reload.is_alive()

        release_snapshot.set()
        poll.join(timeout=5)
        reload.join(timeout=5)
        assert order == ["snapshot", "reload"]
    finally:
        release_snapshot.set()
        app.close()


_TICK = {"prop_id": "tick_model.n_intervals", "value": 1}


def test_tick_renders_published_poll_without_observing(tmp_path: Path) -> None:
    """Render nothing before the first poll, then the published poll, without snapshots."""
    app = TapMap(_runtime_ctx(tmp_path))
    try:
        snapshot_calls: list[None] = []

        def _counting_snapshot() -> dict[str, Any]:
            """Count the snapshot and return one mapped connection."""
            snapshot_calls.append(None)
            return {"connections": [_mapped_candidate(service_scope="PUBLIC")]}

        app.model.snapshot = _counting_snapshot
        spec = _callback_by_outputs_and_input(app, _POLL_OUTPUTS, ("tick_model", "n_intervals"))

        before_poll = _run_callback(spec, _TICK, 1, None, None, False, None, None)
        app.poll_once()
        first_tick = _run_callback(spec, _TICK, 2, None, None, False, None, None)
        second_tick = _run_callback(spec, _TICK, 3, None, None, False, None, first_tick[0])

        assert before_poll == (dash.no_update,) * 5
        assert first_tick[0]["connections"] == second_tick[0]["connections"]
        assert "runtime_info" in first_tick[0]
        assert len(snapshot_calls) == 1
    finally:
        app.close()


def test_tick_during_running_poll_renders_previous_completed_poll(tmp_path: Path) -> None:
    """Render the last completed poll immediately while the next snapshot is still running."""
    app = TapMap(_runtime_ctx(tmp_path))
    snapshot_started = threading.Event()
    release_snapshot = threading.Event()
    try:
        app.model.snapshot = lambda: {"connections": [], "stats": {"poll": "first"}}
        app.poll_once()

        def _blocking_snapshot() -> dict[str, Any]:
            """Signal that the snapshot started, then return once released."""
            snapshot_started.set()
            release_snapshot.wait(timeout=5)
            return {"connections": [], "stats": {"poll": "second"}}

        app.model.snapshot = _blocking_snapshot
        poll = threading.Thread(target=app.poll_once)
        poll.start()
        assert snapshot_started.wait(timeout=5)
        spec = _callback_by_outputs_and_input(app, _POLL_OUTPUTS, ("tick_model", "n_intervals"))

        rendered = _run_callback(spec, _TICK, 2, None, None, False, None, {"stats": {}})

        assert rendered[0]["stats"] == {"poll": "first"}
        release_snapshot.set()
        poll.join(timeout=5)
    finally:
        release_snapshot.set()
        app.close()


def test_close_stops_poller_before_final_save_and_resource_shutdown(tmp_path: Path) -> None:
    """Stop the poller before the final history save and before closing GeoInfo."""
    app = TapMap(_runtime_ctx(tmp_path))
    app.model.snapshot = lambda: {"connections": []}
    first_poll_done = threading.Event()

    def _poll() -> None:
        """Poll once and signal it."""
        app.poll_once()
        first_poll_done.set()

    app._poller_thread = start_poller_thread(_poll, 0.01, app.lifecycle)
    assert first_poll_done.wait(timeout=5)
    is_poller_alive_at: dict[str, bool] = {}
    real_save_history = app._save_history

    def _record_save_history() -> None:
        """Record whether the poller is alive at the final save, then save."""
        is_poller_alive_at["save"] = app._poller_thread.is_alive()
        real_save_history()

    def _record_geoinfo_close() -> None:
        """Record whether the poller is alive when GeoInfo closes."""
        is_poller_alive_at["geoinfo_close"] = app._poller_thread.is_alive()

    app._save_history = _record_save_history
    app.model.geoinfo.close = _record_geoinfo_close

    app.close()

    assert is_poller_alive_at == {"save": False, "geoinfo_close": False}


def test_close_with_stuck_poller_saves_and_keeps_lock_file_and_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Save, keep the lock file, and leave GeoInfo open when the poller does not stop."""
    monkeypatch.setattr(app_module, "POLLER_JOIN_TIMEOUT_S", 0.05)
    app = TapMap(_runtime_ctx(tmp_path))
    release_poller = threading.Event()
    app._poller_thread = threading.Thread(target=release_poller.wait, args=(5,), daemon=True)
    app._poller_thread.start()
    geoinfo_close_calls: list[None] = []
    app.model.geoinfo.close = lambda: geoinfo_close_calls.append(None)
    try:
        with caplog.at_level(logging.ERROR, logger="tapmap.app"):
            app.close()

        assert "Background poller did not stop" in caplog.text
        assert app.insights_path.exists()
        assert app._lock_path.exists()
        assert geoinfo_close_calls == []
    finally:
        release_poller.set()


def test_close_with_poller_stuck_holding_state_lock_skips_save_without_hanging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Return from close() and skip the final save when a stuck poller holds _state_lock."""
    monkeypatch.setattr(app_module, "POLLER_JOIN_TIMEOUT_S", 0.05)
    monkeypatch.setattr(app_module, "SHUTDOWN_LOCK_TIMEOUT_S", 0.05)
    app = TapMap(_runtime_ctx(tmp_path))
    release_poller = threading.Event()

    def _hold_state_lock() -> None:
        """Hold _state_lock until released."""
        with app._state_lock:
            release_poller.wait(timeout=5)

    app._poller_thread = threading.Thread(target=_hold_state_lock, daemon=True)
    app._poller_thread.start()
    try:
        closer = threading.Thread(target=app.close)
        with caplog.at_level(logging.ERROR, logger="tapmap.app"):
            closer.start()
            closer.join(timeout=2)

        assert not closer.is_alive()
        assert "History save skipped" in caplog.text
        assert not app.insights_path.exists()
        assert app._lock_path.exists()
    finally:
        release_poller.set()


def test_render_modal_shows_unavailable_message_when_significant_connection_is_gone() -> None:
    """The detail screen shows a clear message, not an empty modal, when the event is gone."""
    app = _bare_app()

    children, body_class = app._render_modal(
        {
            "screen": "menu_significant_connection_detail",
            "t": "2026-01-01T00:00:00",
            "payload": {
                "timestamp": "2026-08-23T18:42:16.013313",
                "pid": 7920,
                "ip": "8.8.8.8",
                "port": 443,
                "proto": "tcp",
            },
        },
        None,
        None,
        "",
        None,
        False,
        False,
    )

    assert body_class == "modal-body"
    assert any(
        isinstance(c, html.Pre) and "no longer available" in c.children for c in children
    )


def _render_insights_entry(app: TapMap, category: str, value: str) -> list:
    """Render the Insights entry detail screen for category/value."""
    children, _body_class = app._render_modal(
        {
            "screen": "menu_insights_entry",
            "t": "2026-01-01T00:00:00",
            "payload": {"category": category, "value": value},
        },
        None,
        None,
        "",
        None,
        False,
        False,
    )
    return children


class _FixedDatetime(datetime):
    """Provide a fixed current time for Insights entry rendering."""

    @classmethod
    def now(cls, tz: Any = None) -> _FixedDatetime:
        """Return 2026-10-23 12:00."""
        return cls(2026, 10, 23, 12, 0)


def _insights_detail_value(children: list, label: str) -> Any:
    """Return the value cell content for label in the Insights entry detail table."""
    for component in children:
        if not isinstance(component, html.Table):
            continue
        tbody = next(c for c in component.children if isinstance(c, html.Tbody))
        for tr in tbody.children:
            key_cell, value_cell = tr.children
            if key_cell.children == label:
                return value_cell.children
    return None


def test_render_modal_shows_insights_entry_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Insights entry screen renders history from the current Insights state."""
    monkeypatch.setattr("tapmap.app.datetime", _FixedDatetime)
    today_day = _FixedDatetime.now().date().toordinal()
    app = _bare_app()
    app.insights_state = InsightsState(
        version=CURRENT_SCHEMA_VERSION,
        insights={"applications": {"Firefox": {"l": today_day, "m": 1 | 1 << 3 | 1 << 10}}},
        verification_failed={},
    )

    children = _render_insights_entry(app, "applications", "Firefox")

    assert children[0].children == "Firefox"
    assert _insights_detail_value(children, "Active days") == "3 of the last 30 days"


def test_render_modal_shows_unavailable_message_when_insights_entry_is_gone() -> None:
    """Show an unavailable message when the entry is missing."""
    app = _bare_app()
    app.insights_state = InsightsState(
        version=CURRENT_SCHEMA_VERSION,
        insights={"applications": {}},
        verification_failed={},
    )

    children = _render_insights_entry(app, "applications", "Firefox")

    assert any(
        isinstance(c, html.Pre) and "no longer available" in c.children for c in children
    )


def _kv_value(children: list, label: str) -> str | None:
    """Find the value for a given key across every kv_table row in children."""
    for component in children:
        if not isinstance(component, html.Table):
            continue
        tbody = next((c for c in component.children if isinstance(c, html.Tbody)), None)
        if tbody is None:
            continue
        for tr in tbody.children:
            key_cell, value_cell = tr.children
            if key_cell.children == label:
                return value_cell.children.children
    return None


def test_render_modal_menu_about_reflects_the_live_notifications_toggle(tmp_path: Path) -> None:
    """About's Desktop notifications row follows the passed-in toggle state, not runtime_info."""
    app = TapMap(_runtime_ctx(tmp_path))
    try:
        modal_state = {"screen": "menu_about", "t": "2026-01-01T00:00:00", "payload": {}}
        snapshot = {"runtime_info": {"desktop_notifications_available": True}}

        enabled_children, _ = app._render_modal(
            modal_state, snapshot, None, "", None, False, True
        )
        disabled_children, _ = app._render_modal(
            modal_state, snapshot, None, "", None, False, False
        )

        assert _kv_value(enabled_children, "Desktop notifications") == "On"
        assert _kv_value(disabled_children, "Desktop notifications") == "Off"
    finally:
        app.close()


_ACTIVE_MAXMIND_STATUS: dict[str, object] = {
    "provider": "maxmind",
    "city_installed": True,
    "asn_installed": True,
    "city_valid": True,
    "asn_valid": True,
    "local_version": "2026-09-15",
    "local_city_date": "2026-09-15",
    "local_asn_date": "2026-09-15",
    "local_display_date": "2026-09-15",
    "remote_version": None,
    "update_available": "unknown",
    "message": "MaxMind GeoLite2 databases detected",
    "error": None,
    "checked_at": "2026-01-01T00:00:00",
}


def _walk_components(node: object) -> Iterator[Any]:
    """Yield components from a Dash children tree."""
    if node is None or isinstance(node, (str, int, float)):
        return
    if isinstance(node, (list, tuple)):
        for item in node:
            yield from _walk_components(item)
        return
    yield node
    yield from _walk_components(getattr(node, "children", None))


def _has_class(children: object, class_name: str) -> bool:
    """Return whether a component tree contains the CSS class."""
    return any(
        class_name in (getattr(c, "className", "") or "") for c in _walk_components(children)
    )


def _find_by_id(children: object, component_id: str) -> Any | None:
    """Return the component with the requested ID, if present."""
    return next(
        (c for c in _walk_components(children) if getattr(c, "id", None) == component_id),
        None,
    )


@pytest.mark.parametrize(
    "modal_state_data",
    [
        pytest.param(None, id="modal_closed"),
        pytest.param(
            {"screen": "menu_about", "t": "2026-01-01T00:00:00", "payload": {}},
            id="different_screen",
        ),
    ],
)
def test_render_geodb_status_returns_none_when_geodb_screen_not_open(
    tmp_path: Path, modal_state_data: dict[str, object] | None
) -> None:
    """Ignore GeoDB events when its management screen is not open."""
    app = TapMap(_runtime_ctx(tmp_path))
    try:
        children = app._render_geodb_status(
            {"action": "update", "response": _ACTIVE_MAXMIND_STATUS}, modal_state_data
        )
        assert children is None
    finally:
        app.close()


def test_render_geodb_status_renders_result_without_a_loading_placeholder(
    tmp_path: Path,
) -> None:
    """Render completed GeoDB events without the modal loading placeholder."""
    app = TapMap(_runtime_ctx(tmp_path))
    try:
        app.geodb.local_status = MagicMock(return_value=_ACTIVE_MAXMIND_STATUS)
        modal_state = {
            "screen": app.SCR_GEODB_MANAGEMENT,
            "t": "2026-01-01T00:00:00",
            "payload": {},
        }
        geodb_event = {
            "action": "update",
            "response": {
                **_ACTIVE_MAXMIND_STATUS,
                "message": "Databases are already up to date",
                "error": None,
                "update_available": "no",
                "checked_at": "2026-01-01T00:00:05",
            },
        }

        children = app._render_geodb_status(geodb_event, modal_state)

        assert children is not None
        assert not _has_class(children, "mx-spinner")
        assert not _has_class(children, "mx-modal-loading")
        status_node = _find_by_id(children, "geodb-status-text")
        assert status_node is not None
        assert status_node.children == "Databases are already up to date"
    finally:
        app.close()


def test_render_geodb_status_hides_stale_event_before_modal_opened(tmp_path: Path) -> None:
    """Ignore GeoDB events created before the current modal session."""
    app = TapMap(_runtime_ctx(tmp_path))
    try:
        app.geodb.local_status = MagicMock(return_value=_ACTIVE_MAXMIND_STATUS)
        modal_state = {
            "screen": app.SCR_GEODB_MANAGEMENT,
            "t": "2026-01-01T00:00:10",
            "payload": {},
        }
        stale_event = {
            "action": "update",
            "response": {
                **_ACTIVE_MAXMIND_STATUS,
                "message": "Databases are already up to date",
                "error": None,
                "checked_at": "2026-01-01T00:00:00",
            },
        }

        children = app._render_geodb_status(stale_event, modal_state)

        status_node = _find_by_id(children, "geodb-status-text")
        assert status_node is not None
        assert status_node.children == ""
    finally:
        app.close()


def _callback_by_outputs_and_input(
    app: TapMap, outputs: set[tuple[str, str]], input_id: tuple[str, str]
) -> dict[str, Any]:
    """Return the callback matching the requested outputs and input."""
    matches = []
    for spec in app.app.callback_map.values():
        raw_output = spec["output"]
        items = raw_output if isinstance(raw_output, list) else [raw_output]
        ids = {(o.component_id, o.component_property) for o in items}
        if ids != outputs:
            continue
        input_ids = {(i["id"], i["property"]) for i in spec["inputs"]}
        if input_id in input_ids:
            matches.append(spec)
    assert len(matches) == 1, (
        f"expected exactly one callback with outputs {outputs} and input {input_id}, "
        f"found {len(matches)}"
    )
    return matches[0]


def _run_callback(spec: dict[str, Any], triggered: dict[str, Any], *args: Any) -> Any:
    """Call a registered callback's function with a single triggered input."""
    context = copy_context()

    def run() -> Any:
        """Set the Dash callback context and invoke the callback."""
        context_value.set(AttributeDict(triggered_inputs=[triggered]))
        return spec["callback"].__wrapped__(*args)

    return context.run(run)


_RESET_RELAYOUT = {
    "geo.fitbounds": False,
    "geo.projection.scale": 1,
    "geo.center.lon": 0,
    "geo.center.lat": 0,
    "geo.projection.rotation.lon": 0,
}


@pytest.mark.parametrize(
    ("relayout_data", "expected"),
    [
        (_RESET_RELAYOUT, (None, None)),
        (
            {"geo.center.lon": 10.5, "geo.center.lat": 59.9, "geo.projection.scale": 2},
            (dash.no_update, dash.no_update),
        ),
        ({"geo.projection.scale": 4}, (dash.no_update, dash.no_update)),
        (None, (dash.no_update, dash.no_update)),
    ],
)
def test_map_reset_callback_clears_selection_only_on_reset(
    tmp_path: Path, relayout_data: Any, expected: tuple[Any, Any]
) -> None:
    """Clear selection and relayout data on Reset; preserve both for other events."""
    app = TapMap(_runtime_ctx(tmp_path))
    try:
        spec = _callback_by_outputs_and_input(
            app,
            {("selected_country", "data"), ("map", "relayoutData")},
            ("map", "relayoutData"),
        )

        result = _run_callback(
            spec, {"prop_id": "map.relayoutData", "value": relayout_data}, relayout_data
        )

        assert result == expected
    finally:
        app.close()


def test_zoom_connections_still_clears_selected_country(tmp_path: Path) -> None:
    """Clear country selection and enable connection fitting for the zoom action."""
    app = TapMap(_runtime_ctx(tmp_path))
    try:
        spec = _callback_by_outputs_and_input(
            app,
            {("selected_country", "data"), ("camera_mode", "data")},
            ("key_action", "data"),
        )
        key_action = {"action": ACTION_ZOOM_CONNECTIONS, "t": "2026-10-23T12:00:00"}

        result = _run_callback(
            spec, {"prop_id": "key_action.data", "value": key_action}, key_action, [], "NO", None
        )

        assert result == (None, "connections")
    finally:
        app.close()


def test_modal_shell_no_longer_has_geodb_event_as_an_input(tmp_path: Path) -> None:
    """Keep GeoDB events from triggering the modal loading shell."""
    app = TapMap(_runtime_ctx(tmp_path))
    try:
        spec = _callback_by_outputs_and_input(
            app,
            {
                ("modal_overlay", "className"),
                ("modal_body", "children"),
                ("modal_body", "className"),
                ("modal_content_request", "data"),
            },
            ("modal_state", "data"),
        )
        input_ids = {(i["id"], i["property"]) for i in spec["inputs"]}
        state_ids = {(i["id"], i["property"]) for i in spec["state"]}

        assert ("geodb_event", "data") not in input_ids
        assert input_ids == {("modal_state", "data")}
        assert ("geodb_event", "data") in state_ids
    finally:
        app.close()


def test_geodb_status_renderer_reacts_to_geodb_event_only(tmp_path: Path) -> None:
    """Trigger GeoDB status rendering only from GeoDB events."""
    app = TapMap(_runtime_ctx(tmp_path))
    try:
        spec = _callback_by_outputs_and_input(
            app, {("modal_body", "children")}, ("geodb_event", "data")
        )
        input_ids = {(i["id"], i["property"]) for i in spec["inputs"]}
        state_ids = {(i["id"], i["property"]) for i in spec["state"]}

        assert input_ids == {("geodb_event", "data")}
        assert ("modal_state", "data") in state_ids
    finally:
        app.close()


def _app_for_runtime_info(tmp_path: Path) -> TapMap:
    """Build a minimal TapMap instance for runtime-info tests."""
    app = object.__new__(TapMap)
    app.runtime = _runtime_ctx(tmp_path)
    app.geodb = MagicMock()
    app.geodb.local_status.return_value = {"provider": "none", "local_display_date": "-"}
    app.model = SimpleNamespace(geoinfo=SimpleNamespace(city_enabled=False))
    app._public_ip_cached = None
    app._auto_geo_cached = {}
    app.my_location = []
    app.desktop_notification_channel = None
    return app


def test_build_runtime_info_reports_mqtt_unconfigured_when_no_config_file(
    tmp_path: Path,
) -> None:
    """With no mqtt.json in the app data directory, MQTT reads as unconfigured."""
    app = _app_for_runtime_info(tmp_path)

    info = app._build_runtime_info()

    assert info["mqtt_configured"] is False
    assert info["mqtt_host"] is None
    assert info["mqtt_port"] is None
    assert info["mqtt_topic"] is None
    assert info["mqtt_tls"] is None


def test_build_runtime_info_reports_mqtt_config_without_leaking_credentials(
    tmp_path: Path,
) -> None:
    """A configured mqtt.json surfaces host/port/topic/tls but never the stored credentials."""
    app = _app_for_runtime_info(tmp_path)
    save_mqtt_config(
        mqtt_config_path(tmp_path),
        MqttConfig(
            host="192.0.2.1",
            port=8883,
            topic="tapmap/events",
            tls=True,
            username="secret-user",
            password="secret-pass",
        ),
    )

    info = app._build_runtime_info()

    assert info["mqtt_configured"] is True
    assert info["mqtt_host"] == "192.0.2.1"
    assert info["mqtt_port"] == 8883
    assert info["mqtt_topic"] == "tapmap/events"
    assert info["mqtt_tls"] is True
    assert info["notification_learning_days"] == app.runtime.notification_learning_days
    assert "secret-user" not in info.values()
    assert "secret-pass" not in info.values()


def test_build_runtime_info_reports_installed_dash_version(tmp_path: Path) -> None:
    """Verify reported Dash version."""
    app = _app_for_runtime_info(tmp_path)

    info = app._build_runtime_info()

    assert info["dash_version"] == dash.__version__


def test_build_runtime_info_reports_desktop_notifications_unavailable_without_a_channel(
    tmp_path: Path,
) -> None:
    """With no desktop notification channel, availability reads as False."""
    app = _app_for_runtime_info(tmp_path)
    app.desktop_notification_channel = None

    info = app._build_runtime_info()

    assert info["desktop_notifications_available"] is False


def test_build_runtime_info_reports_desktop_notifications_available_with_a_channel(
    tmp_path: Path,
) -> None:
    """With a desktop notification channel present, availability reads as True."""
    app = _app_for_runtime_info(tmp_path)
    app.desktop_notification_channel = SimpleNamespace(enabled=True)

    info = app._build_runtime_info()

    assert info["desktop_notifications_available"] is True


# SHA-256 of dist/TwemojiCountryFlags.woff2 in country-flag-emoji-polyfill 0.1.10,
# as recorded in third_party/THIRD_PARTY_NOTICES.md.
_FLAG_FONT_SHA256 = "9f04f14429bb6a9f415c7a4dd902a918d7e81a4f7526c415496fdb063954e3b8"


def test_flag_font_is_served_unmodified(tmp_path: Path) -> None:
    """Serve the bundled flag font from assets, matching the recorded checksum."""
    app = TapMap(_runtime_ctx(tmp_path))
    try:
        response = app.app.server.test_client().get("/assets/TwemojiCountryFlags.woff2")

        assert response.status_code == 200
        assert hashlib.sha256(response.data).hexdigest() == _FLAG_FONT_SHA256
    finally:
        app.close()
