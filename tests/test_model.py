"""Test classification helpers in model.Model."""

from typing import Any

from tapmap.model.model import CacheItem, Model

_APP_CACHE_ITEM_FIELDS = {
    "app_name",
    "app_creator",
    "app_trust",
    "app_signature_state",
    "app_signature_state_reason",
}


def test_service_scope_classifies_addresses() -> None:
    """Verify service scope classification for common address types."""
    assert Model._service_scope("127.0.0.1") == "LOCAL"
    assert Model._service_scope("::1") == "LOCAL"
    assert Model._service_scope("192.168.1.10") == "LAN"
    assert Model._service_scope("fe80::1") == "LAN"
    assert Model._service_scope("8.8.8.8") == "PUBLIC"
    assert Model._service_scope(None) == "UNKNOWN"
    assert Model._service_scope("bad-ip") == "UNKNOWN"


def test_bind_scope_classifies_addresses() -> None:
    """Verify bind scope classification for common bind addresses."""
    assert Model._bind_scope("127.0.0.1") == "LOCAL"
    assert Model._bind_scope("::1") == "LOCAL"
    assert Model._bind_scope("192.168.1.10") == "LAN"
    assert Model._bind_scope("fe80::1") == "LAN"
    assert Model._bind_scope("8.8.8.8") == "PUBLIC"
    assert Model._bind_scope("0.0.0.0") == "PUBLIC"
    assert Model._bind_scope("::") == "PUBLIC"
    assert Model._bind_scope(None) == "UNKNOWN"
    assert Model._bind_scope("bad-ip") == "UNKNOWN"


def test_is_map_candidate_requires_public_scope_and_coordinates() -> None:
    """Verify map candidate classification requires PUBLIC scope and coordinates."""
    assert (
        Model._is_map_candidate(
            {
                "service_scope": "PUBLIC",
                "lat": 59.91,
                "lon": 10.75,
            }
        )
        is True
    )

    assert (
        Model._is_map_candidate(
            {
                "service_scope": "LAN",
                "lat": 59.91,
                "lon": 10.75,
            }
        )
        is False
    )

    assert (
        Model._is_map_candidate(
            {
                "service_scope": "PUBLIC",
                "lat": None,
                "lon": 10.75,
            }
        )
        is False
    )

    assert (
        Model._is_map_candidate(
            {
                "service_scope": "PUBLIC",
                "lat": 59.91,
                "lon": None,
            }
        )
        is False
    )

    assert (
        Model._is_map_candidate(
            {
                "service_scope": "UNKNOWN",
                "lat": 59.91,
                "lon": 10.75,
            }
        )
        is False
    )


# --- snapshot() / AppInfo integration ---


class FakeNetInfo:
    """Return a fixed list of connection records."""

    def __init__(self, connections: list[dict[str, Any]]) -> None:
        self._connections = connections

    def get_data(self) -> list[dict[str, Any]]:
        """Return the fixed connection records."""
        return self._connections


class FakeGeoInfo:
    """Disabled GeoInfo stand-in; geo enrichment is out of scope for these tests."""

    enabled = False


class FakeAppInfo:
    """AppInfo stand-in with a configurable enabled flag and enrich() behavior."""

    def __init__(self, *, enabled: bool, enrich_fn: Any = None) -> None:
        self.enabled = enabled
        self.enrich_calls = 0
        self._enrich_fn = enrich_fn

    def enrich(self, connections: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Track invocation and optionally mutate connections in place."""
        self.enrich_calls += 1
        if self._enrich_fn is not None:
            self._enrich_fn(connections)
        return connections


def _established_tcp_connection(**overrides: Any) -> dict[str, Any]:
    """Return a minimal established TCP connection to a public address."""
    conn = {
        "proto": "tcp",
        "status": "ESTABLISHED",
        "raddr_ip": "8.8.8.8",
        "raddr_port": 443,
        "pid": 1234,
        "process_label": "firefox.exe",
        "exe": r"C:\Program Files\Mozilla Firefox\firefox.exe",
        "cmdline": ["firefox.exe"],
        "process_status": "OK",
    }
    conn.update(overrides)
    return conn


def _set_app_fields(connections: list[dict[str, Any]]) -> None:
    """Populate app_* fields on every connection, simulating a real AppInfo.enrich()."""
    for conn in connections:
        conn["app_name"] = "Firefox"
        conn["app_creator"] = "Mozilla Corporation"
        conn["app_trust"] = "trusted"
        conn["app_signature_state"] = "SignedAndTrusted"
        conn["app_signature_state_reason"] = "None"


def test_cache_item_key_set_matches_contract() -> None:
    """Pin the full CacheItem key set so an accidental rename fails a test, not the UI."""
    assert set(CacheItem.__annotations__) == {
        "proto",
        "ip",
        "port",
        "service",
        "service_hint",
        "service_scope",
        "lat",
        "lon",
        "pid",
        "process_name",
        "exe",
        "cmdline",
        "process_status",
        "city",
        "country",
        "country_code",
        "asn",
        "asn_org",
        *_APP_CACHE_ITEM_FIELDS,
    }


def test_snapshot_copies_app_fields_into_cache_item() -> None:
    """CacheItem carries all app_* fields set by AppInfo.enrich()."""
    model = Model(
        netinfo=FakeNetInfo([_established_tcp_connection()]),
        geoinfo=FakeGeoInfo(),
        appinfo=FakeAppInfo(enabled=True, enrich_fn=_set_app_fields),
    )

    snap = model.snapshot()

    assert snap["error"] is False
    assert len(snap["cache_items"]) == 1
    item = snap["cache_items"][0]
    assert item["app_name"] == "Firefox"
    assert item["app_creator"] == "Mozilla Corporation"
    assert item["app_trust"] == "trusted"
    assert item["app_signature_state"] == "SignedAndTrusted"
    assert item["app_signature_state_reason"] == "None"


def test_snapshot_stats_reflects_appinfo_enabled() -> None:
    """stats['appinfo_enabled'] mirrors AppInfo.enabled in both states."""
    for enabled in (True, False):
        model = Model(
            netinfo=FakeNetInfo([_established_tcp_connection()]),
            geoinfo=FakeGeoInfo(),
            appinfo=FakeAppInfo(enabled=enabled),
        )

        snap = model.snapshot()

        assert snap["stats"]["appinfo_enabled"] is enabled


def test_snapshot_does_not_call_enrich_when_appinfo_disabled() -> None:
    """AppInfo.enrich() is never called when AppInfo.enabled is False."""
    appinfo = FakeAppInfo(enabled=False, enrich_fn=_set_app_fields)
    model = Model(
        netinfo=FakeNetInfo([_established_tcp_connection()]),
        geoinfo=FakeGeoInfo(),
        appinfo=appinfo,
    )

    snap = model.snapshot()

    assert appinfo.enrich_calls == 0
    item = snap["cache_items"][0]
    for field in _APP_CACHE_ITEM_FIELDS:
        assert item[field] is None


def test_snapshot_app_fields_default_to_none_when_unset() -> None:
    """CacheItem app_* fields fall back to None when AppInfo does not set them.

    This covers any reason a connection ends up without app data (AppInfo
    could not resolve it, chose to skip it, etc.) - Model's own contract is
    only to surface whatever AppInfo did or didn't provide, via CacheItem's
    established conn.get(...) defaulting pattern already used for geo fields.
    """
    model = Model(
        netinfo=FakeNetInfo([_established_tcp_connection()]),
        geoinfo=FakeGeoInfo(),
        appinfo=FakeAppInfo(enabled=True),  # enrich() is a no-op: sets nothing
    )

    snap = model.snapshot()

    item = snap["cache_items"][0]
    for field in _APP_CACHE_ITEM_FIELDS:
        assert item[field] is None


def test_snapshot_map_candidate_shares_app_fields_with_cache_item() -> None:
    """A map candidate is the same object as its cache_items entry, app fields included."""

    def _set_app_and_geo_fields(connections: list[dict[str, Any]]) -> None:
        # A public IP with no lat/lon is not a map candidate; add coordinates
        # directly, since GeoInfo enrichment itself is out of scope here.
        _set_app_fields(connections)
        for conn in connections:
            conn["lat"] = 37.4
            conn["lon"] = -122.1

    model = Model(
        netinfo=FakeNetInfo([_established_tcp_connection()]),
        geoinfo=FakeGeoInfo(),
        appinfo=FakeAppInfo(enabled=True, enrich_fn=_set_app_and_geo_fields),
    )

    snap = model.snapshot()

    assert len(snap["map_candidates"]) == 1
    assert snap["map_candidates"][0] is snap["cache_items"][0]
    assert snap["map_candidates"][0]["app_name"] == "Firefox"
