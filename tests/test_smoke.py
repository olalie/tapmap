"""Smoke tests for TapMap application bootstrap."""

import dataclasses
import platform
from pathlib import Path
from typing import Any

import pytest

import tapmap
from tapmap import app as app_module
from tapmap.app import APP_META, TapMap, _build_arg_parser
from tapmap.autostart import macos_autostart, windows_autostart
from tapmap.runtime import RuntimeContext
from tapmap.state.autostart import (
    AutostartDecision,
    ClickAction,
    DisplayState,
    WriteOutcome,
)


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


def _runtime_ctx(tmp_path: Path, *, is_docker: bool = False) -> RuntimeContext:
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
        is_docker=is_docker,
        location_override=None,
        security_extensions_dir=tmp_path,
        tray_icon_path=tmp_path / "tapmap.ico",
    )


def _modal_state_store_data(app: TapMap):
    """Return initial modal_state store data from app layout."""
    for child in app.app.layout.children:
        if getattr(child, "id", None) == "modal_state":
            return child.data
    raise AssertionError("modal_state store not found")


def _component_exists(node: Any, component_id: str) -> bool:
    """Return True when a component id exists in a Dash component tree."""
    return _find_component(node, component_id) is not None


def _find_component(node: Any, component_id: str) -> Any:
    """Find a component by ID in a Dash component tree."""
    if getattr(node, "id", None) == component_id:
        return node

    children = getattr(node, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            found = _find_component(child, component_id)
            if found is not None:
                return found
        return None
    if children is None:
        return None
    return _find_component(children, component_id)


def test_tapmap_module_imports() -> None:
    """Import the application module."""
    assert tapmap is not None


def test_no_browser_flag_defaults_to_false() -> None:
    """Keep browser launch enabled by default."""
    args = _build_arg_parser().parse_args([])
    assert args.no_browser is False


def test_no_browser_flag_parses_true() -> None:
    """Disable browser launch with --no-browser."""
    args = _build_arg_parser().parse_args(["--no-browser"])
    assert args.no_browser is True


def test_tapmap_app_constructs(tmp_path: Path) -> None:
    """Construct TapMap without starting the server."""
    runtime_ctx = _runtime_ctx(tmp_path)
    app = TapMap(runtime_ctx)
    try:
        assert app.app is not None
    finally:
        app.close()


def test_create_tray_icon_returns_none_for_docker(tmp_path: Path, monkeypatch) -> None:
    """Do not create a tray icon in Docker."""
    app = TapMap(_runtime_ctx(tmp_path, is_docker=True))
    try:
        called = False

        def _fake_create_tray_icon(**_kwargs):
            nonlocal called
            called = True
            return object()

        monkeypatch.setattr(app_module, "create_tray_icon", _fake_create_tray_icon)

        icon = app._create_tray_icon()

        assert icon is None
        assert called is False
    finally:
        app.close()


def test_create_tray_icon_wires_open_and_quit_callbacks(tmp_path: Path, monkeypatch) -> None:
    """Connect the tray Open and Quit actions to TapMap."""
    app = TapMap(_runtime_ctx(tmp_path))
    try:
        captured: dict[str, Any] = {}

        def _fake_create_tray_icon(*, icon_path, tooltip, on_open, on_quit):
            captured["icon_path"] = icon_path
            captured["tooltip"] = tooltip
            captured["on_open"] = on_open
            captured["on_quit"] = on_quit
            return object()

        monkeypatch.setattr(app_module, "create_tray_icon", _fake_create_tray_icon)
        opened_urls: list[str] = []
        monkeypatch.setattr(
            app_module.webbrowser, "open", lambda url, new=0: opened_urls.append(url)
        )

        icon = app._create_tray_icon()

        assert icon is not None
        assert captured["icon_path"] == app.runtime.tray_icon_path
        assert captured["tooltip"] == app.runtime.meta.name

        captured["on_open"]()
        assert opened_urls == [app._server_url()]

        captured["on_quit"]()
        app.lifecycle.wait_for_shutdown()  # must not block: on_quit() already requested it
    finally:
        app.close()


def test_tapmap_startup_opens_geodb_management_modal_when_no_provider(tmp_path: Path) -> None:
    """Startup opens GeoDB management when no provider is available."""
    app = TapMap(_runtime_ctx(tmp_path))
    try:
        modal_state = _modal_state_store_data(app)
        assert modal_state is not None
        assert modal_state["screen"] == app.SCR_GEODB_MANAGEMENT
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


def test_resolve_maxmind_install_credentials_prefers_ui_values(monkeypatch, tmp_path: Path) -> None:
    """UI MaxMind credentials override stored values when both are present."""
    app = TapMap(_runtime_ctx(tmp_path))
    try:
        monkeypatch.setattr(
            app.geodb.maxmind,
            "stored_credentials",
            lambda: ("stored-account", "stored-license"),
        )

        account_id, license_key = app._resolve_maxmind_install_credentials(
            "ui-account",
            "ui-license",
        )

        assert account_id == "ui-account"
        assert license_key == "ui-license"
    finally:
        app.close()


def test_resolve_maxmind_install_credentials_falls_back_to_stored_values(
    monkeypatch, tmp_path: Path
) -> None:
    """Blank UI MaxMind fields fall back to stored keyring values."""
    app = TapMap(_runtime_ctx(tmp_path))
    try:
        monkeypatch.setattr(
            app.geodb.maxmind,
            "stored_credentials",
            lambda: ("stored-account", "stored-license"),
        )

        account_id, license_key = app._resolve_maxmind_install_credentials("", "")

        assert account_id == "stored-account"
        assert license_key == "stored-license"
    finally:
        app.close()


def test_install_maxmind_requires_credentials(monkeypatch, tmp_path: Path) -> None:
    """Install returns an error when no credentials are available."""
    app = TapMap(_runtime_ctx(tmp_path))
    try:
        monkeypatch.setattr(
            app.geodb.maxmind,
            "stored_credentials",
            lambda: ("", ""),
        )

        response = app._handle_geo_install_maxmind(
            "",
            "",
        )

        assert response["error"] == "credentials_invalid"
        assert response["message"] == "Account ID and license key are required"

    finally:
        app.close()


def test_install_maxmind_rejects_invalid_credentials(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Install returns the validator error when credentials are invalid."""
    app = TapMap(_runtime_ctx(tmp_path))
    try:
        monkeypatch.setattr(
            app.geodb.maxmind,
            "stored_credentials",
            lambda: ("", ""),
        )

        def _raise_invalid(
            _account_id: str,
            _license_key: str,
        ) -> None:
            raise ValueError("Invalid MaxMind credentials")

        monkeypatch.setattr(
            app.geodb.maxmind,
            "validate_credentials",
            _raise_invalid,
        )

        response = app._handle_geo_install_maxmind(
            "bad-account",
            "bad-license",
        )

        assert response["error"] == "credentials_invalid"
        assert response["message"] == "Invalid MaxMind credentials"

    finally:
        app.close()

def test_startup_geodb_modal_should_close_when_recheck_enables_geoinfo(
    tmp_path: Path,
) -> None:
    """Startup GeoDB modal closes once the post-install snapshot reports geoinfo enabled."""
    app = TapMap(_runtime_ctx(tmp_path))
    try:
        modal_state = {
            "screen": app.SCR_GEODB_MANAGEMENT,
            "t": "2026-06-04T00:00:00",
            "payload": {"startup_required": True},
        }
        snapshot = {"runtime_info": {"geoinfo_enabled": True}}

        assert app._startup_geodb_modal_should_close(modal_state, snapshot) is True
        assert app._startup_geodb_modal_should_close(modal_state, {"runtime_info": {}}) is False
        assert app._startup_geodb_modal_should_close(None, snapshot) is False
    finally:
        app.close()

def test_handle_geo_update_success(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Return update response when update and runtime reload succeed."""
    app = TapMap(_runtime_ctx(tmp_path))

    try:
        monkeypatch.setattr(
            app.geodb,
            "update",
            lambda: {
                "provider": "dbip",
                "message": "Databases are already up to date",
                "error": None,
                "checked_at": "2026-06-01T12:00:00",
            },
        )

        monkeypatch.setattr(
            app,
            "_reload_geodb_runtime",
            lambda: True,
        )

        result = app._handle_geo_update()

        assert result["provider"] == "dbip"
        assert result["error"] is None
        assert result["message"] == "Databases are already up to date"
        assert result["checked_at"] == "2026-06-01T12:00:00"

    finally:
        app.close()

def test_handle_geo_update_reload_failed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Append reload failure when runtime reload fails."""
    app = TapMap(_runtime_ctx(tmp_path))

    try:
        monkeypatch.setattr(
            app.geodb,
            "update",
            lambda: {
                "provider": "dbip",
                "message": "Databases are already up to date",
                "error": None,
                "checked_at": "2026-06-01T12:00:00",
            },
        )

        monkeypatch.setattr(
            app,
            "_reload_geodb_runtime",
            lambda: False,
        )

        result = app._handle_geo_update()

        assert result["provider"] == "dbip"
        assert result["error"] == "reload_failed"
        assert result["message"] == (
            "Databases are already up to date Runtime reload failed."
        )

    finally:
        app.close()

def test_handle_geo_update_preserves_original_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Keep update failure information when update already failed."""
    app = TapMap(_runtime_ctx(tmp_path))

    try:
        monkeypatch.setattr(
            app.geodb,
            "update",
            lambda: {
                "provider": "dbip",
                "message": "Unable to update databases",
                "error": "download_failed",
                "checked_at": "2026-06-01T12:00:00",
            },
        )

        monkeypatch.setattr(
            app,
            "_reload_geodb_runtime",
            lambda: True,
        )

        result = app._handle_geo_update()

        assert result["provider"] == "dbip"
        assert result["error"] == "download_failed"
        assert result["message"] == "Unable to update databases"

    finally:
        app.close()


# --- "Run TapMap automatically" control: trigger classification ---


def test_autostart_trigger_kind_button_click_is_act() -> None:
    """Treat an autostart button click as an action."""
    assert (
        TapMap._autostart_trigger_kind(
            trigger="menu_autostart", menu_open=False, n_clicks=1, key_action=None
        )
        == "act"
    )
    assert (
        TapMap._autostart_trigger_kind(
            trigger="menu_autostart", menu_open=False, n_clicks=0, key_action=None
        )
        == "ignore"
    )


def test_autostart_trigger_kind_r_keyboard_mnemonic_is_act() -> None:
    """Treat the R shortcut as an autostart action."""
    kind = TapMap._autostart_trigger_kind(
        trigger="key_action",
        menu_open=False,
        n_clicks=None,
        key_action={"action": "menu_autostart", "t": "2026-01-01T00:00:00"},
    )
    assert kind == "act"


def test_autostart_trigger_kind_unrelated_key_action_is_ignored() -> None:
    """Ignore unrelated keyboard actions."""
    kind = TapMap._autostart_trigger_kind(
        trigger="key_action",
        menu_open=False,
        n_clicks=None,
        key_action={"action": "menu_help", "t": "2026-01-01T00:00:00"},
    )
    assert kind == "ignore"


def test_autostart_trigger_kind_menu_opening_is_refresh() -> None:
    """Refresh autostart state when the menu opens."""
    assert (
        TapMap._autostart_trigger_kind(
            trigger="menu_open", menu_open=True, n_clicks=None, key_action=None
        )
        == "refresh"
    )
    assert (
        TapMap._autostart_trigger_kind(
            trigger="menu_open", menu_open=False, n_clicks=None, key_action=None
        )
        == "ignore"
    )


# --- "Run TapMap automatically" control: platform gating and wiring ---


def test_autostart_button_present_on_windows_desktop(tmp_path: Path, monkeypatch) -> None:
    """Show the autostart control on Windows desktop."""
    monkeypatch.setattr(app_module.platform, "system", lambda: "Windows")

    app = TapMap(_runtime_ctx(tmp_path))
    try:
        assert _component_exists(app.app.layout, "menu_autostart") is True
    finally:
        app.close()


def test_autostart_button_absent_on_unsupported_platform(tmp_path: Path, monkeypatch) -> None:
    """Hide the autostart control on unsupported platforms."""
    monkeypatch.setattr(app_module.platform, "system", lambda: "Linux")

    app = TapMap(_runtime_ctx(tmp_path))
    try:
        assert _component_exists(app.app.layout, "menu_autostart") is False
    finally:
        app.close()


def test_autostart_button_absent_for_docker(tmp_path: Path, monkeypatch) -> None:
    """Hide the autostart control in Docker."""
    monkeypatch.setattr(app_module.platform, "system", lambda: "Windows")

    app = TapMap(_runtime_ctx(tmp_path, is_docker=True))
    try:
        assert _component_exists(app.app.layout, "menu_autostart") is False
    finally:
        app.close()


def test_autostart_button_disabled_for_a_source_run(tmp_path: Path, monkeypatch) -> None:
    """Disable the autostart control for a source run."""
    monkeypatch.setattr(app_module.platform, "system", lambda: "Windows")

    app = TapMap(_runtime_ctx(tmp_path))
    try:
        button = _find_component(app.app.layout, "menu_autostart")
        assert button is not None
        assert button.disabled is True
    finally:
        app.close()


def test_initial_autostart_disabled_reflects_click_action_not_is_frozen(
    tmp_path: Path, monkeypatch
) -> None:
    """Disable the autostart control when no click action is available."""
    monkeypatch.setattr(app_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        windows_autostart,
        "query_display_state",
        lambda **_kwargs: AutostartDecision(DisplayState.ON, ClickAction.NONE),
    )

    runtime_ctx = dataclasses.replace(_runtime_ctx(tmp_path), is_frozen=True)
    app = TapMap(runtime_ctx)
    try:
        button = _find_component(app.app.layout, "menu_autostart")
        assert button is not None
        assert button.disabled is True
        assert "is-checked" in button.className
    finally:
        app.close()


def test_autostart_click_routes_to_disable_when_currently_on(tmp_path: Path, monkeypatch) -> None:
    """Disable autostart when the current state is on."""
    monkeypatch.setattr(app_module.platform, "system", lambda: "Windows")

    app = TapMap(_runtime_ctx(tmp_path))
    try:
        monkeypatch.setattr(
            windows_autostart,
            "query_display_state",
            lambda **_kwargs: AutostartDecision(DisplayState.ON, ClickAction.DISABLE),
        )
        calls: list[str] = []
        monkeypatch.setattr(
            windows_autostart,
            "disable",
            lambda **_kwargs: calls.append("disable") or (WriteOutcome.OK, None),
        )

        assert app._handle_autostart_click() is None
        assert calls == ["disable"]
    finally:
        app.close()


def test_autostart_disabled_returns_true_only_for_click_action_none() -> None:
    """Disable the control only when the click action is NONE."""
    assert TapMap._autostart_disabled(AutostartDecision(DisplayState.ON, ClickAction.NONE)) is True
    assert (
        TapMap._autostart_disabled(AutostartDecision(DisplayState.OFF, ClickAction.NONE)) is True
    )
    assert (
        TapMap._autostart_disabled(AutostartDecision(DisplayState.ON, ClickAction.DISABLE))
        is False
    )
    assert (
        TapMap._autostart_disabled(AutostartDecision(DisplayState.OFF, ClickAction.CREATE))
        is False
    )


def test_autostart_click_never_writes_when_click_action_is_none(
    tmp_path: Path, monkeypatch
) -> None:
    """Do not write when the click action is NONE."""
    monkeypatch.setattr(app_module.platform, "system", lambda: "Windows")

    app = TapMap(_runtime_ctx(tmp_path))
    try:

        def _fail(**_kwargs):
            raise AssertionError("must not write when click_action is NONE")

        monkeypatch.setattr(windows_autostart, "disable", _fail)
        monkeypatch.setattr(windows_autostart, "enable", _fail)
        monkeypatch.setattr(windows_autostart, "create", _fail)
        monkeypatch.setattr(windows_autostart, "repair_and_enable", _fail)

        for display_state in (DisplayState.ON, DisplayState.OFF, DisplayState.UNAVAILABLE):
            monkeypatch.setattr(
                windows_autostart,
                "query_display_state",
                lambda ds=display_state, **_kwargs: AutostartDecision(ds, ClickAction.NONE),
            )

            assert app._handle_autostart_click() is None
    finally:
        app.close()


def test_autostart_click_does_not_raise_on_write_time_conflict(
    tmp_path: Path, monkeypatch
) -> None:
    """Handle a task ownership conflict without raising."""
    monkeypatch.setattr(app_module.platform, "system", lambda: "Windows")

    app = TapMap(_runtime_ctx(tmp_path))
    try:
        monkeypatch.setattr(
            windows_autostart,
            "query_display_state",
            lambda **_kwargs: AutostartDecision(DisplayState.ON, ClickAction.DISABLE),
        )
        monkeypatch.setattr(
            windows_autostart, "disable", lambda **_kwargs: (WriteOutcome.CONFLICT, None)
        )

        assert app._handle_autostart_click() is None
    finally:
        app.close()


def test_autostart_click_logs_warning_on_write_error(tmp_path: Path, monkeypatch) -> None:
    """Log a warning when an autostart write fails."""
    monkeypatch.setattr(app_module.platform, "system", lambda: "Windows")

    app = TapMap(_runtime_ctx(tmp_path))
    try:
        monkeypatch.setattr(
            windows_autostart,
            "query_display_state",
            lambda **_kwargs: AutostartDecision(DisplayState.ON, ClickAction.DISABLE),
        )
        monkeypatch.setattr(
            windows_autostart, "disable", lambda **_kwargs: (WriteOutcome.ERROR, "access denied")
        )
        warnings: list[str] = []
        monkeypatch.setattr(
            app.logger, "warning", lambda msg, *args: warnings.append(msg % args)
        )

        assert app._handle_autostart_click() is None
        assert warnings == ["Autostart write failed: access denied"]
    finally:
        app.close()


# --- "Run TapMap automatically" control: Darwin dispatch ---


def test_autostart_button_present_on_macos_desktop(tmp_path: Path, monkeypatch) -> None:
    """Show the autostart control on macOS desktop."""
    monkeypatch.setattr(app_module.platform, "system", lambda: "Darwin")

    app = TapMap(_runtime_ctx(tmp_path))
    try:
        assert _component_exists(app.app.layout, "menu_autostart") is True
    finally:
        app.close()


def test_startup_setup_dispatches_to_macos_backend_on_darwin(
    tmp_path: Path, monkeypatch
) -> None:
    """Route initial autostart setup to the macOS backend on Darwin."""
    monkeypatch.setattr(app_module.platform, "system", lambda: "Darwin")
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        macos_autostart, "run_startup_setup", lambda **kwargs: calls.append(kwargs)
    )

    app = TapMap(_runtime_ctx(tmp_path))
    try:
        assert calls == [{"app_data_dir": tmp_path, "is_frozen": False}]
    finally:
        app.close()


def test_current_autostart_decision_dispatches_to_macos_backend_on_darwin(
    tmp_path: Path, monkeypatch
) -> None:
    """Route the autostart decision query to the macOS backend on Darwin."""
    monkeypatch.setattr(app_module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        macos_autostart,
        "query_display_state",
        lambda **_kwargs: AutostartDecision(DisplayState.ON, ClickAction.DISABLE),
    )

    app = TapMap(_runtime_ctx(tmp_path))
    try:
        assert app._current_autostart_decision() == AutostartDecision(
            DisplayState.ON, ClickAction.DISABLE
        )
    finally:
        app.close()


def test_macos_autostart_click_routes_to_disable_when_currently_on(
    tmp_path: Path, monkeypatch
) -> None:
    """Disable macOS autostart when the current state is on."""
    monkeypatch.setattr(app_module.platform, "system", lambda: "Darwin")

    app = TapMap(_runtime_ctx(tmp_path))
    try:
        monkeypatch.setattr(
            macos_autostart,
            "query_display_state",
            lambda **_kwargs: AutostartDecision(DisplayState.ON, ClickAction.DISABLE),
        )
        calls: list[str] = []
        monkeypatch.setattr(
            macos_autostart,
            "disable",
            lambda: calls.append("disable") or (WriteOutcome.OK, None),
        )

        assert app._handle_autostart_click() is None
        assert calls == ["disable"]
    finally:
        app.close()


def test_macos_autostart_click_routes_to_create_when_currently_off(
    tmp_path: Path, monkeypatch
) -> None:
    """Register with SMAppService.mainApp when the current state is off."""
    monkeypatch.setattr(app_module.platform, "system", lambda: "Darwin")

    app = TapMap(_runtime_ctx(tmp_path))
    try:
        monkeypatch.setattr(
            macos_autostart,
            "query_display_state",
            lambda **_kwargs: AutostartDecision(DisplayState.OFF, ClickAction.CREATE),
        )
        calls: list[str] = []
        monkeypatch.setattr(
            macos_autostart,
            "create",
            lambda: calls.append("create") or (WriteOutcome.OK, None),
        )

        assert app._handle_autostart_click() is None
        assert calls == ["create"]
    finally:
        app.close()


def test_macos_autostart_click_routes_to_recover_and_enable_when_not_found(
    tmp_path: Path, monkeypatch
) -> None:
    """Run the notFound recovery sequence when the current state is notFound."""
    monkeypatch.setattr(app_module.platform, "system", lambda: "Darwin")

    app = TapMap(_runtime_ctx(tmp_path))
    try:
        monkeypatch.setattr(
            macos_autostart,
            "query_display_state",
            lambda **_kwargs: AutostartDecision(
                DisplayState.UNAVAILABLE, ClickAction.RECOVER_AND_ENABLE
            ),
        )
        calls: list[str] = []
        monkeypatch.setattr(
            macos_autostart,
            "recover_and_enable",
            lambda: calls.append("recover_and_enable") or (WriteOutcome.OK, None),
        )

        assert app._handle_autostart_click() is None
        assert calls == ["recover_and_enable"]
    finally:
        app.close()


def test_macos_autostart_click_opens_settings_when_requires_approval(
    tmp_path: Path, monkeypatch
) -> None:
    """Open System Settings, without a write outcome, when the current state is requiresApproval."""
    monkeypatch.setattr(app_module.platform, "system", lambda: "Darwin")

    app = TapMap(_runtime_ctx(tmp_path))
    try:
        monkeypatch.setattr(
            macos_autostart,
            "query_display_state",
            lambda **_kwargs: AutostartDecision(DisplayState.OFF, ClickAction.OPEN_SETTINGS),
        )
        calls: list[str] = []
        monkeypatch.setattr(
            macos_autostart, "open_settings", lambda: calls.append("open_settings")
        )

        assert app._handle_autostart_click() is None
        assert calls == ["open_settings"]
    finally:
        app.close()


def test_macos_autostart_click_never_writes_when_click_action_is_none(
    tmp_path: Path, monkeypatch
) -> None:
    """Do not write when the click action is NONE."""
    monkeypatch.setattr(app_module.platform, "system", lambda: "Darwin")

    app = TapMap(_runtime_ctx(tmp_path))
    try:

        def _fail(**_kwargs):
            raise AssertionError("must not write when click_action is NONE")

        monkeypatch.setattr(macos_autostart, "disable", _fail)
        monkeypatch.setattr(macos_autostart, "create", _fail)
        monkeypatch.setattr(macos_autostart, "recover_and_enable", _fail)
        monkeypatch.setattr(macos_autostart, "open_settings", _fail)

        for display_state in (DisplayState.ON, DisplayState.OFF, DisplayState.UNAVAILABLE):
            monkeypatch.setattr(
                macos_autostart,
                "query_display_state",
                lambda ds=display_state, **_kwargs: AutostartDecision(ds, ClickAction.NONE),
            )

            assert app._handle_autostart_click() is None
    finally:
        app.close()


def test_macos_autostart_click_logs_warning_on_write_error(tmp_path: Path, monkeypatch) -> None:
    """Log a warning when a macOS autostart write fails."""
    monkeypatch.setattr(app_module.platform, "system", lambda: "Darwin")

    app = TapMap(_runtime_ctx(tmp_path))
    try:
        monkeypatch.setattr(
            macos_autostart,
            "query_display_state",
            lambda **_kwargs: AutostartDecision(DisplayState.ON, ClickAction.DISABLE),
        )
        monkeypatch.setattr(
            macos_autostart, "disable", lambda: (WriteOutcome.ERROR, "access denied")
        )
        warnings: list[str] = []
        monkeypatch.setattr(app.logger, "warning", lambda msg, *args: warnings.append(msg % args))

        assert app._handle_autostart_click() is None
        assert warnings == ["Autostart write failed: access denied"]
    finally:
        app.close()


# --- macOS post-start browser decision (login-launch Apple Event) ---


def test_macos_browser_decision_is_deferred_when_all_conditions_met(
    tmp_path: Path, monkeypatch
) -> None:
    """Defer the browser decision on a frozen, non-Docker Darwin build with browser launch on."""
    monkeypatch.setattr(app_module.platform, "system", lambda: "Darwin")
    runtime_ctx = dataclasses.replace(_runtime_ctx(tmp_path), is_frozen=True, launch_browser=True)
    app = TapMap(runtime_ctx)
    try:
        assert app._macos_browser_decision_is_deferred() is True
    finally:
        app.close()


@pytest.mark.parametrize(
    ("system", "is_frozen", "launch_browser", "is_docker"),
    [
        pytest.param("Darwin", False, True, False, id="source_run"),
        pytest.param("Darwin", True, False, False, id="browser_policy_already_off"),
        pytest.param("Darwin", True, True, True, id="docker"),
        # Keep is_frozen False to avoid invoking the Windows Task Scheduler backend.
        pytest.param("Windows", False, True, False, id="non_darwin_platform"),
    ],
)
def test_macos_browser_decision_not_deferred_when_a_condition_is_unmet(
    tmp_path: Path, monkeypatch, system: str, is_frozen: bool, launch_browser: bool, is_docker: bool
) -> None:
    """Do not defer the browser decision unless every deferral condition is met."""
    monkeypatch.setattr(app_module.platform, "system", lambda: system)
    runtime_ctx = dataclasses.replace(
        _runtime_ctx(tmp_path, is_docker=is_docker),
        is_frozen=is_frozen,
        launch_browser=launch_browser,
    )
    app = TapMap(runtime_ctx)
    try:
        assert app._macos_browser_decision_is_deferred() is False
    finally:
        app.close()


def test_macos_browser_decision_opens_browser_for_manual_launch(
    tmp_path: Path, monkeypatch
) -> None:
    """Open the browser when the launch event carries no login-item signal."""
    app = TapMap(_runtime_ctx(tmp_path))
    try:
        calls: list[str] = []
        monkeypatch.setattr(app, "_open_browser", lambda _url: calls.append("opened"))

        app._macos_browser_decision("http://example.test/", is_login_launch=False)

        assert calls == ["opened"]
    finally:
        app.close()


def test_macos_browser_decision_suppresses_browser_for_login_launch(
    tmp_path: Path, monkeypatch
) -> None:
    """Suppress the browser when the launch event carries the login-item signal."""
    app = TapMap(_runtime_ctx(tmp_path))
    try:

        def _fail(_url):
            raise AssertionError("must not open the browser for a login launch")

        monkeypatch.setattr(app, "_open_browser", _fail)

        app._macos_browser_decision("http://example.test/", is_login_launch=True)
    finally:
        app.close()


@pytest.mark.skipif(
    platform.system() != "Darwin", reason="requires PyObjC to import macos_login_launch"
)
def test_decide_browser_open_installs_login_launch_handler_when_tray_available(
    tmp_path: Path, monkeypatch
) -> None:
    """Defer to the macOS login-launch handler when a tray icon is available."""
    monkeypatch.setattr(app_module.platform, "system", lambda: "Darwin")
    runtime_ctx = dataclasses.replace(_runtime_ctx(tmp_path), is_frozen=True, launch_browser=True)
    app = TapMap(runtime_ctx)
    try:
        calls: list[str] = []
        monkeypatch.setattr(
            "tapmap.autostart.macos_login_launch.install",
            lambda _callback: calls.append("installed"),
        )

        app._decide_browser_open("http://example.test/", object())

        assert calls == ["installed"]
    finally:
        app.close()


def test_decide_browser_open_falls_back_safely_when_tray_unavailable(
    tmp_path: Path, monkeypatch
) -> None:
    """Do not open the browser, and never attempt the handler, when no tray icon exists."""
    monkeypatch.setattr(app_module.platform, "system", lambda: "Darwin")
    runtime_ctx = dataclasses.replace(_runtime_ctx(tmp_path), is_frozen=True, launch_browser=True)
    app = TapMap(runtime_ctx)
    try:

        def _fail(_url):
            raise AssertionError("must not open the browser when the tray is unavailable")

        monkeypatch.setattr(app, "_open_browser", _fail)

        app._decide_browser_open("http://example.test/", None)
    finally:
        app.close()


@pytest.mark.skipif(
    platform.system() != "Darwin", reason="requires PyObjC to import macos_login_launch"
)
def test_decide_browser_open_falls_back_safely_when_install_fails(
    tmp_path: Path, monkeypatch
) -> None:
    """Do not open the browser, and do not raise, when installing the handler fails."""
    monkeypatch.setattr(app_module.platform, "system", lambda: "Darwin")
    runtime_ctx = dataclasses.replace(_runtime_ctx(tmp_path), is_frozen=True, launch_browser=True)
    app = TapMap(runtime_ctx)
    try:

        def _raise(_callback):
            raise RuntimeError("boom")

        monkeypatch.setattr("tapmap.autostart.macos_login_launch.install", _raise)

        def _fail(_url):
            raise AssertionError("must not open the browser when installation fails")

        monkeypatch.setattr(app, "_open_browser", _fail)

        app._decide_browser_open("http://example.test/", object())
    finally:
        app.close()


# --- "Run TapMap automatically" control: unsupported-platform dispatch ---


def test_current_autostart_decision_is_unavailable_on_an_unsupported_platform(
    tmp_path: Path, monkeypatch
) -> None:
    """Report unavailable, rather than running Windows logic, on an unsupported platform."""
    monkeypatch.setattr(app_module.platform, "system", lambda: "Linux")

    def _fail(**_kwargs):
        raise AssertionError("must not call the Windows backend on an unsupported platform")

    monkeypatch.setattr(windows_autostart, "query_display_state", _fail)

    app = TapMap(_runtime_ctx(tmp_path))
    try:
        assert app._current_autostart_decision() == AutostartDecision(
            DisplayState.UNAVAILABLE, ClickAction.NONE
        )
    finally:
        app.close()


def test_autostart_click_is_a_noop_on_an_unsupported_platform(
    tmp_path: Path, monkeypatch
) -> None:
    """Do nothing, rather than running Windows logic, on an unsupported platform."""
    monkeypatch.setattr(app_module.platform, "system", lambda: "Linux")

    def _fail(**_kwargs):
        raise AssertionError("must not call the Windows backend on an unsupported platform")

    monkeypatch.setattr(windows_autostart, "query_display_state", _fail)
    monkeypatch.setattr(windows_autostart, "disable", _fail)
    monkeypatch.setattr(windows_autostart, "enable", _fail)
    monkeypatch.setattr(windows_autostart, "create", _fail)
    monkeypatch.setattr(windows_autostart, "repair_and_enable", _fail)

    app = TapMap(_runtime_ctx(tmp_path))
    try:
        assert app._handle_autostart_click() is None
    finally:
        app.close()
