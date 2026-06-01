"""Smoke tests for TapMap application bootstrap."""

from pathlib import Path
from typing import Any

import tapmap
from tapmap import app as app_module
from tapmap.app import APP_META, TapMap
from tapmap.runtime import RuntimeContext, build_runtime
from tapmap.state.status_cache import StatusCache


class _FakeReader:
    """Minimal MaxMind reader stub for startup/recheck tests."""

    def __init__(self) -> None:
        self.closed = False

    def metadata(self):
        class Meta:
            build_epoch = 1_714_521_600

        return Meta()

    def get(self, _ip):
        return None

    def close(self):
        self.closed = True


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
        is_docker=False,
        location_override=None,
    )


def _modal_state_store_data(app: TapMap):
    """Return initial modal_state store data from app layout."""
    for child in app.app.layout.children:
        if getattr(child, "id", None) == "modal_state":
            return child.data
    raise AssertionError("modal_state store not found")


def _component_exists(node: Any, component_id: str) -> bool:
    """Return True when a component id exists in a Dash component tree."""
    if getattr(node, "id", None) == component_id:
        return True

    children = getattr(node, "children", None)
    if isinstance(children, (list, tuple)):
        return any(_component_exists(child, component_id) for child in children)
    if children is None:
        return False
    return _component_exists(children, component_id)


def test_tapmap_module_imports() -> None:
    """Import the application module."""
    assert tapmap is not None


def test_tapmap_app_constructs(tmp_path: Path) -> None:
    """Construct TapMap without starting the server."""
    runtime_ctx = _runtime_ctx(tmp_path)
    app = TapMap(runtime_ctx)
    try:
        assert app.app is not None
    finally:
        app.close()


def test_tapmap_startup_opens_missing_geo_modal_when_no_provider(tmp_path: Path) -> None:
    """Startup opens the existing missing-GeoIP modal when no provider is available."""
    app = TapMap(_runtime_ctx(tmp_path))
    try:
        modal_state = _modal_state_store_data(app)
        assert modal_state is not None
        assert modal_state["screen"] == app.SCR_MISSING_GEO_DB
    finally:
        app.close()


def test_tapmap_layout_has_geodb_management_menu_entry_not_legacy_recheck(
    tmp_path: Path,
) -> None:
    """Menu includes GeoDB management and no longer includes legacy recheck command."""
    app = TapMap(_runtime_ctx(tmp_path))
    try:
        assert _component_exists(app.app.layout, "menu_geodb_management") is True
        assert _component_exists(app.app.layout, "menu_recheck_geoip") is False
    finally:
        app.close()


def test_tapmap_startup_skips_missing_geo_modal_when_dbip_pair_is_available(
    monkeypatch, tmp_path: Path
) -> None:
    """Startup does not open the missing-GeoIP modal when DB-IP files are available."""
    monkeypatch.setattr(
        app_module.GeoDbService,
        "local_status",
        lambda _self: {
            "provider": "dbip",
            "city_installed": True,
            "asn_installed": True,
            "city_valid": True,
            "asn_valid": True,
            "local_version": "2026-06",
            "local_city_date": "2026-06-01",
            "local_asn_date": "2026-06-01",
            "local_display_date": "2026-06-01",
            "remote_version": None,
            "update_available": "unknown",
            "busy": False,
            "message": "DB-IP Lite databases detected",
            "error": None,
        },
    )

    app = TapMap(_runtime_ctx(tmp_path))
    try:
        modal_state = _modal_state_store_data(app)
        assert modal_state is None
    finally:
        app.close()


def test_tapmap_startup_skips_missing_geo_modal_when_maxmind_pair_is_available(
    monkeypatch, tmp_path: Path
) -> None:
    """Startup does not open the missing-GeoIP modal when MaxMind files are available."""
    monkeypatch.setattr(
        app_module.GeoDbService,
        "local_status",
        lambda _self: {
            "provider": "maxmind",
            "city_installed": True,
            "asn_installed": True,
            "city_valid": True,
            "asn_valid": True,
            "local_version": "1714521600",
            "local_city_date": "2024-05-01",
            "local_asn_date": "2024-05-01",
            "local_display_date": "2024-05-01",
            "remote_version": None,
            "update_available": "unknown",
            "busy": False,
            "message": "MaxMind GeoLite2 databases detected",
            "error": None,
        },
    )

    app = TapMap(_runtime_ctx(tmp_path))
    try:
        modal_state = _modal_state_store_data(app)
        assert modal_state is None
    finally:
        app.close()


def test_recheck_uses_geodb_status_and_geoinfo_reload_for_supported_provider(
    monkeypatch, tmp_path: Path
) -> None:
    """Recheck succeeds when a supported provider pair is present and GeoInfo reloads."""
    monkeypatch.setattr(
        app_module.GeoDbService,
        "recheck",
        lambda _self: {
            "provider": "dbip",
            "city_installed": True,
            "asn_installed": True,
            "city_valid": True,
            "asn_valid": True,
            "local_version": "2026-06",
            "local_city_date": "2026-06-01",
            "local_asn_date": "2026-06-01",
            "local_display_date": "2026-06-01",
            "remote_version": None,
            "update_available": "unknown",
            "busy": False,
            "message": "DB-IP Lite databases detected",
            "error": None,
        },
    )

    app = TapMap(_runtime_ctx(tmp_path))
    try:
        monkeypatch.setattr(app, "_resolve_my_location", lambda: [])
        monkeypatch.setattr(app.model, "snapshot", lambda: {"stats": {}, "cache_items": []})
        monkeypatch.setattr(app.model.geoinfo, "reload", lambda: True)
        app.model.geoinfo._city_reader = _FakeReader()

        snap, cache, _status_store, _view, flash = app._handle_geo_recheck(StatusCache())

        assert cache == {}
        assert isinstance(snap, dict)
        assert snap["app_info"]["geoinfo_enabled"] is True
        assert isinstance(flash, dict)
        assert flash["message"] == "Databases loaded. Geolocation enabled."
    finally:
        app.close()
