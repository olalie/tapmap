"""Test macOS autostart behavior.

SMAppService.mainApp and AppKit calls are mocked throughout, so tests never
register/unregister a real login item and never touch a real AppKit event
loop.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# macos_login_launch imports PyObjC (objc/AppKit/Foundation) at module level,
# which is unavailable outside macOS - skip collecting this whole file rather
# than error on platforms where it can't be imported.
pytest.importorskip("objc")

from tapmap.autostart import macos_autostart, macos_login_launch, marker
from tapmap.autostart import macos_service_management as service_management
from tapmap.state.autostart import (
    ClickAction,
    DisplayState,
    MacosMainAppStatus,
    WriteOutcome,
)

# --- macos_service_management.query_status() ---


@pytest.mark.parametrize(
    ("raw_status", "expected"),
    [
        pytest.param(0, MacosMainAppStatus.NOT_REGISTERED, id="not_registered"),
        pytest.param(1, MacosMainAppStatus.ENABLED, id="enabled"),
        pytest.param(2, MacosMainAppStatus.REQUIRES_APPROVAL, id="requires_approval"),
        pytest.param(3, MacosMainAppStatus.NOT_FOUND, id="not_found"),
    ],
)
def test_query_status_maps_raw_value(
    monkeypatch, raw_status: int, expected: MacosMainAppStatus
) -> None:
    """Map SMAppService status values."""
    monkeypatch.setattr(service_management, "_raw_status", lambda: raw_status)
    assert service_management.query_status() == expected


def test_query_status_raises_on_unexpected_value(monkeypatch) -> None:
    """Raise for an unknown SMAppService status."""
    monkeypatch.setattr(service_management, "_raw_status", lambda: 99)

    with pytest.raises(service_management.ServiceManagementError):
        service_management.query_status()


def test_query_status_raises_on_framework_failure(monkeypatch) -> None:
    """Raise when SMAppService status cannot be read."""

    def _raise():
        raise RuntimeError("framework unavailable")

    monkeypatch.setattr(service_management, "_raw_status", _raise)

    with pytest.raises(service_management.ServiceManagementError):
        service_management.query_status()


# --- macos_service_management.register() / unregister() ---


class _FakeNSError:
    """Stand-in for an NSError carrying a description and a numeric code."""

    def __init__(self, description: str, code: int) -> None:
        self._description = description
        self._code = code

    def __str__(self) -> str:
        return self._description

    def code(self) -> int:
        return self._code


class _FakeMainApp:
    """Stand-in for SMAppService.mainAppService() in tests."""

    def __init__(self, *, register_result=(True, None), unregister_result=(True, None)):
        self._register_result = register_result
        self._unregister_result = unregister_result
        self.register_calls = 0
        self.unregister_calls = 0

    def registerAndReturnError_(self, _error):
        self.register_calls += 1
        return self._register_result

    def unregisterAndReturnError_(self, _error):
        self.unregister_calls += 1
        return self._unregister_result


def test_register_succeeds(monkeypatch) -> None:
    """Do not raise when registerAndReturnError_ reports success."""
    fake = _FakeMainApp()
    monkeypatch.setattr(service_management, "_main_app", lambda: fake)
    service_management.register()
    assert fake.register_calls == 1


def test_register_raises_on_failure(monkeypatch) -> None:
    """Raise ServiceManagementError, carrying the NSError code, on failure."""
    fake = _FakeMainApp(register_result=(False, _FakeNSError("boom", 12)))
    monkeypatch.setattr(service_management, "_main_app", lambda: fake)

    with pytest.raises(service_management.ServiceManagementError, match="boom") as excinfo:
        service_management.register()
    assert excinfo.value.code == 12


def test_unregister_succeeds(monkeypatch) -> None:
    """Do not raise when unregisterAndReturnError_ reports success."""
    fake = _FakeMainApp()
    monkeypatch.setattr(service_management, "_main_app", lambda: fake)
    service_management.unregister()
    assert fake.unregister_calls == 1


def test_unregister_raises_on_failure(monkeypatch) -> None:
    """Raise ServiceManagementError, carrying the NSError code, on failure."""
    fake = _FakeMainApp(unregister_result=(False, _FakeNSError("boom", 6)))
    monkeypatch.setattr(service_management, "_main_app", lambda: fake)

    with pytest.raises(service_management.ServiceManagementError, match="boom") as excinfo:
        service_management.unregister()
    assert excinfo.value.code == 6


def test_open_system_settings_login_items_calls_the_native_api(monkeypatch) -> None:
    """Call SMAppService.openSystemSettingsLoginItems() directly."""
    import sys
    import types

    calls: list[str] = []

    class _FakeSMAppService:
        @staticmethod
        def openSystemSettingsLoginItems():
            calls.append("opened")

    fake_module = types.ModuleType("ServiceManagement")
    fake_module.SMAppService = _FakeSMAppService
    monkeypatch.setitem(sys.modules, "ServiceManagement", fake_module)

    service_management.open_system_settings_login_items()

    assert calls == ["opened"]


# --- macos_autostart.query_display_state() ---


def test_query_display_state_is_off_for_a_source_run_and_never_queries(monkeypatch) -> None:
    """Do not query SMAppService for a source run."""

    def _fail():
        raise AssertionError("must not query for a source run")

    monkeypatch.setattr(service_management, "query_status", _fail)

    decision = macos_autostart.query_display_state(is_frozen=False)

    assert decision.display_state == DisplayState.OFF
    assert decision.click_action == ClickAction.NONE


def test_query_display_state_on_when_enabled(monkeypatch) -> None:
    """Show ENABLED as on with a disable action."""
    monkeypatch.setattr(service_management, "query_status", lambda: MacosMainAppStatus.ENABLED)

    decision = macos_autostart.query_display_state(is_frozen=True)

    assert decision.display_state == DisplayState.ON
    assert decision.click_action == ClickAction.DISABLE


def test_query_display_state_unavailable_when_query_raises(monkeypatch) -> None:
    """Show autostart as unavailable when SMAppService cannot be queried."""

    def _raise():
        raise service_management.ServiceManagementError("boom")

    monkeypatch.setattr(service_management, "query_status", _raise)

    decision = macos_autostart.query_display_state(is_frozen=True)

    assert decision.display_state == DisplayState.UNAVAILABLE
    assert decision.click_action == ClickAction.NONE


# --- macos_autostart.create() ---


@pytest.mark.parametrize(
    "confirmed_status",
    [
        pytest.param(MacosMainAppStatus.ENABLED, id="enabled"),
        pytest.param(MacosMainAppStatus.REQUIRES_APPROVAL, id="requires_approval"),
    ],
)
def test_create_succeeds_when_register_and_status_agree(
    monkeypatch, confirmed_status: MacosMainAppStatus
) -> None:
    """Report success for ENABLED or REQUIRES_APPROVAL."""
    monkeypatch.setattr(service_management, "register", lambda: None)
    monkeypatch.setattr(service_management, "query_status", lambda: confirmed_status)

    outcome, error = macos_autostart.create()

    assert outcome == WriteOutcome.OK
    assert error is None


def test_create_reports_error_when_register_call_fails(monkeypatch) -> None:
    """Report an error when register() itself raises."""

    def _raise():
        raise service_management.ServiceManagementError("boom")

    monkeypatch.setattr(service_management, "register", _raise)

    outcome, error = macos_autostart.create()

    assert outcome == WriteOutcome.ERROR
    assert error == "boom"


def test_create_reports_error_when_post_register_status_is_not_confirmed(monkeypatch) -> None:
    """Report an error when register() succeeds but activation isn't confirmed."""
    monkeypatch.setattr(service_management, "register", lambda: None)
    monkeypatch.setattr(
        service_management, "query_status", lambda: MacosMainAppStatus.NOT_REGISTERED
    )

    outcome, error = macos_autostart.create()

    assert outcome == WriteOutcome.ERROR
    assert "not_registered" in error


def test_create_reports_error_when_post_register_query_fails(monkeypatch) -> None:
    """Report an error when the post-register status query itself fails."""
    monkeypatch.setattr(service_management, "register", lambda: None)

    def _raise():
        raise service_management.ServiceManagementError("boom")

    monkeypatch.setattr(service_management, "query_status", _raise)

    outcome, error = macos_autostart.create()

    assert outcome == WriteOutcome.ERROR
    assert error == "boom"


# --- macos_autostart.recover_and_enable(): NOT_FOUND recovery ---


@pytest.mark.parametrize(
    "confirmed_status",
    [
        pytest.param(MacosMainAppStatus.ENABLED, id="enabled"),
        pytest.param(MacosMainAppStatus.REQUIRES_APPROVAL, id="requires_approval"),
    ],
)
def test_recover_and_enable_succeeds_after_cleanup_unregister(
    monkeypatch, confirmed_status: MacosMainAppStatus
) -> None:
    """Report successful recovery for ENABLED or REQUIRES_APPROVAL."""
    calls: list[str] = []
    monkeypatch.setattr(service_management, "unregister", lambda: calls.append("unregister"))
    monkeypatch.setattr(service_management, "register", lambda: calls.append("register"))
    monkeypatch.setattr(service_management, "query_status", lambda: confirmed_status)

    outcome, error = macos_autostart.recover_and_enable()

    assert outcome == WriteOutcome.OK
    assert error is None
    assert calls == ["unregister", "register"]


def test_recover_and_enable_tolerates_any_cleanup_unregister_error(monkeypatch) -> None:
    """Continue recovery after cleanup errors."""

    def _raise():
        raise service_management.ServiceManagementError("operation not permitted", code=1)

    calls: list[str] = []
    monkeypatch.setattr(service_management, "unregister", _raise)
    monkeypatch.setattr(service_management, "register", lambda: calls.append("register"))
    monkeypatch.setattr(service_management, "query_status", lambda: MacosMainAppStatus.ENABLED)

    outcome, _error = macos_autostart.recover_and_enable()

    assert outcome == WriteOutcome.OK
    assert calls == ["register"]


def test_recover_and_enable_outcome_after_cleanup_failure_follows_register_and_confirm(
    monkeypatch,
) -> None:
    """Determine the outcome by register() + confirm, regardless of cleanup unregister failing."""

    def _raise():
        raise service_management.ServiceManagementError("operation not permitted", code=1)

    monkeypatch.setattr(service_management, "unregister", _raise)
    monkeypatch.setattr(service_management, "register", lambda: None)
    monkeypatch.setattr(service_management, "query_status", lambda: MacosMainAppStatus.NOT_FOUND)

    outcome, error = macos_autostart.recover_and_enable()

    assert outcome == WriteOutcome.ERROR
    assert "not_found" in error


# --- macos_autostart.open_settings() ---


def test_open_settings_calls_the_native_api(monkeypatch) -> None:
    """Call the native open-Login-Items API."""
    calls: list[str] = []
    monkeypatch.setattr(
        service_management, "open_system_settings_login_items", lambda: calls.append("opened")
    )

    macos_autostart.open_settings()

    assert calls == ["opened"]


def test_open_settings_does_not_raise_when_the_native_call_fails(monkeypatch) -> None:
    """Log rather than raise if opening System Settings fails."""

    def _raise():
        raise RuntimeError("boom")

    monkeypatch.setattr(service_management, "open_system_settings_login_items", _raise)

    macos_autostart.open_settings()


# --- macos_autostart.disable() ---


def test_disable_succeeds_when_unregister_and_status_agree(monkeypatch) -> None:
    """Report success when unregister() succeeds and status is NOT_REGISTERED."""
    monkeypatch.setattr(service_management, "unregister", lambda: None)
    monkeypatch.setattr(
        service_management, "query_status", lambda: MacosMainAppStatus.NOT_REGISTERED
    )

    outcome, error = macos_autostart.disable()

    assert outcome == WriteOutcome.OK
    assert error is None


def test_disable_reports_error_when_unregister_call_fails(monkeypatch) -> None:
    """Report an error when unregister() itself raises."""

    def _raise():
        raise service_management.ServiceManagementError("boom")

    monkeypatch.setattr(service_management, "unregister", _raise)

    outcome, error = macos_autostart.disable()

    assert outcome == WriteOutcome.ERROR
    assert error == "boom"


def test_disable_reports_error_when_post_unregister_query_fails(monkeypatch) -> None:
    """Report an error when the post-unregister status query itself fails."""
    monkeypatch.setattr(service_management, "unregister", lambda: None)

    def _raise():
        raise service_management.ServiceManagementError("boom")

    monkeypatch.setattr(service_management, "query_status", _raise)

    outcome, error = macos_autostart.disable()

    assert outcome == WriteOutcome.ERROR
    assert error == "boom"


@pytest.mark.parametrize(
    "unresolved_status",
    [
        pytest.param(MacosMainAppStatus.ENABLED, id="still_enabled"),
        pytest.param(MacosMainAppStatus.REQUIRES_APPROVAL, id="requires_approval"),
        pytest.param(MacosMainAppStatus.NOT_FOUND, id="not_found"),
    ],
)
def test_disable_does_not_treat_anything_but_not_registered_as_success(
    monkeypatch, unresolved_status: MacosMainAppStatus
) -> None:
    """Require NOT_REGISTERED to confirm disable."""
    monkeypatch.setattr(service_management, "unregister", lambda: None)
    monkeypatch.setattr(service_management, "query_status", lambda: unresolved_status)

    outcome, error = macos_autostart.disable()

    assert outcome == WriteOutcome.ERROR
    assert error is not None


def test_disable_never_registers(monkeypatch) -> None:
    """Never perform registration recovery on the OFF path, regardless of outcome."""

    def _fail_register():
        raise AssertionError("disable() must never call register()")

    monkeypatch.setattr(service_management, "unregister", lambda: None)
    monkeypatch.setattr(service_management, "register", _fail_register)
    monkeypatch.setattr(service_management, "query_status", lambda: MacosMainAppStatus.NOT_FOUND)

    macos_autostart.disable()


# --- macos_autostart.run_startup_setup(): the marker-absent state machine ---


def test_startup_setup_noop_for_source_run(tmp_path: Path, monkeypatch) -> None:
    """Do not query or register anything during a source run."""

    def _fail():
        raise AssertionError("must not query for a source run")

    monkeypatch.setattr(service_management, "query_status", _fail)

    macos_autostart.run_startup_setup(app_data_dir=tmp_path, is_frozen=False)

    assert marker.has_completed_setup(tmp_path) is False


def test_startup_setup_noop_once_marker_exists(tmp_path: Path, monkeypatch) -> None:
    """Do not query once the setup marker exists."""
    marker.mark_setup_completed(tmp_path)

    def _fail():
        raise AssertionError("must not query once the marker exists")

    monkeypatch.setattr(service_management, "query_status", _fail)

    macos_autostart.run_startup_setup(app_data_dir=tmp_path, is_frozen=True)


def test_startup_setup_registers_and_writes_marker_when_not_registered(
    tmp_path: Path, monkeypatch
) -> None:
    """Register autostart and write the marker when not registered."""
    calls: list[str] = []
    # First query (the initial check) reports NOT_REGISTERED; the second
    # (inside create()'s confirmation step) reports the post-register result.
    statuses = iter([MacosMainAppStatus.NOT_REGISTERED, MacosMainAppStatus.ENABLED])
    monkeypatch.setattr(service_management, "query_status", lambda: next(statuses))
    monkeypatch.setattr(service_management, "register", lambda: calls.append("register"))

    macos_autostart.run_startup_setup(app_data_dir=tmp_path, is_frozen=True)

    assert calls == ["register"]
    assert marker.has_completed_setup(tmp_path) is True


def test_startup_setup_does_not_write_marker_when_not_registered_activation_unconfirmed(
    tmp_path: Path, monkeypatch
) -> None:
    """Keep the marker absent when create()'s post-register confirmation fails."""
    statuses = iter([MacosMainAppStatus.NOT_REGISTERED, MacosMainAppStatus.NOT_REGISTERED])
    monkeypatch.setattr(service_management, "query_status", lambda: next(statuses))
    monkeypatch.setattr(service_management, "register", lambda: None)

    macos_autostart.run_startup_setup(app_data_dir=tmp_path, is_frozen=True)

    assert marker.has_completed_setup(tmp_path) is False


def test_startup_setup_recovers_and_writes_marker_when_not_found(
    tmp_path: Path, monkeypatch
) -> None:
    """Run the NOT_FOUND recovery sequence and write the marker once enabled."""
    calls: list[str] = []
    statuses = iter([MacosMainAppStatus.NOT_FOUND, MacosMainAppStatus.ENABLED])
    monkeypatch.setattr(service_management, "query_status", lambda: next(statuses))
    monkeypatch.setattr(service_management, "unregister", lambda: calls.append("unregister"))
    monkeypatch.setattr(service_management, "register", lambda: calls.append("register"))

    macos_autostart.run_startup_setup(app_data_dir=tmp_path, is_frozen=True)

    assert calls == ["unregister", "register"]
    assert marker.has_completed_setup(tmp_path) is True


def test_startup_setup_does_not_write_marker_when_not_found_recovery_fails(
    tmp_path: Path, monkeypatch
) -> None:
    """Keep the marker absent when NOT_FOUND recovery leaves status notFound, with no retry."""
    statuses = iter([MacosMainAppStatus.NOT_FOUND, MacosMainAppStatus.NOT_FOUND])
    monkeypatch.setattr(service_management, "query_status", lambda: next(statuses))
    monkeypatch.setattr(service_management, "unregister", lambda: None)
    monkeypatch.setattr(service_management, "register", lambda: None)

    macos_autostart.run_startup_setup(app_data_dir=tmp_path, is_frozen=True)

    assert marker.has_completed_setup(tmp_path) is False
    with pytest.raises(StopIteration):
        next(statuses)


@pytest.mark.parametrize(
    "existing_status",
    [
        pytest.param(MacosMainAppStatus.ENABLED, id="enabled"),
        pytest.param(MacosMainAppStatus.REQUIRES_APPROVAL, id="requires_approval"),
    ],
)
def test_startup_setup_preserves_existing_registration_and_writes_marker(
    tmp_path: Path, monkeypatch, existing_status: MacosMainAppStatus
) -> None:
    """Preserve existing registration and write the marker."""

    def _fail():
        raise AssertionError("must not register when already registered in some form")

    monkeypatch.setattr(service_management, "query_status", lambda: existing_status)
    monkeypatch.setattr(service_management, "register", _fail)

    macos_autostart.run_startup_setup(app_data_dir=tmp_path, is_frozen=True)

    assert marker.has_completed_setup(tmp_path) is True


def test_startup_setup_does_nothing_when_query_fails(tmp_path: Path, monkeypatch) -> None:
    """Make no changes when SMAppService cannot be queried."""

    def _raise():
        raise service_management.ServiceManagementError("boom")

    monkeypatch.setattr(service_management, "query_status", _raise)

    macos_autostart.run_startup_setup(app_data_dir=tmp_path, is_frozen=True)

    assert marker.has_completed_setup(tmp_path) is False


def test_startup_setup_does_not_write_marker_when_registration_fails(
    tmp_path: Path, monkeypatch
) -> None:
    """Keep the marker absent when the initial registration fails."""
    monkeypatch.setattr(
        service_management, "query_status", lambda: MacosMainAppStatus.NOT_REGISTERED
    )

    def _raise():
        raise service_management.ServiceManagementError("permission denied")

    monkeypatch.setattr(service_management, "register", _raise)

    macos_autostart.run_startup_setup(app_data_dir=tmp_path, is_frozen=True)

    assert marker.has_completed_setup(tmp_path) is False


# --- macos_login_launch: Apple Event handler logic ---


class _FakeAEDescriptor:
    """Stand-in for an NSAppleEventDescriptor carrying an enumerated value."""

    def __init__(self, enum_code: int) -> None:
        self._enum_code = enum_code

    def enumCodeValue(self) -> int:
        return self._enum_code


class _FakeAppleEvent:
    """Stand-in for the NSAppleEventDescriptor passed to the AE handler."""

    def __init__(self, prop_data: _FakeAEDescriptor | None = None) -> None:
        self._prop_data = prop_data

    def paramDescriptorForKeyword_(self, _keyword: int) -> _FakeAEDescriptor | None:
        return self._prop_data


def test_handler_reports_login_launch_when_lgit_present() -> None:
    """Report True when keyAEPropData matches keyAELaunchedAsLogInItem."""
    decisions: list[bool] = []
    delegate = macos_login_launch._LoginLaunchDelegate.alloc().initWithCallback_(decisions.append)
    event = _FakeAppleEvent(
        prop_data=_FakeAEDescriptor(macos_login_launch._KEY_AE_LAUNCHED_AS_LOGIN_ITEM)
    )

    delegate.handleAppleEvent_withReplyEvent_(event, None)

    assert decisions == [True]


def test_handler_reports_manual_launch_when_prop_data_absent() -> None:
    """Report False when keyAEPropData is absent."""
    decisions: list[bool] = []
    delegate = macos_login_launch._LoginLaunchDelegate.alloc().initWithCallback_(decisions.append)
    event = _FakeAppleEvent(prop_data=None)

    delegate.handleAppleEvent_withReplyEvent_(event, None)

    assert decisions == [False]


def test_handler_reports_manual_launch_when_enum_code_does_not_match() -> None:
    """Report False when keyAEPropData is present but doesn't match lgit."""
    decisions: list[bool] = []
    delegate = macos_login_launch._LoginLaunchDelegate.alloc().initWithCallback_(decisions.append)
    event = _FakeAppleEvent(prop_data=_FakeAEDescriptor(0x12345678))

    delegate.handleAppleEvent_withReplyEvent_(event, None)

    assert decisions == [False]


def test_handler_invokes_callback_at_most_once() -> None:
    """Do not report the decision again if the event handler fires more than once."""
    decisions: list[bool] = []
    delegate = macos_login_launch._LoginLaunchDelegate.alloc().initWithCallback_(decisions.append)
    event = _FakeAppleEvent(
        prop_data=_FakeAEDescriptor(macos_login_launch._KEY_AE_LAUNCHED_AS_LOGIN_ITEM)
    )

    delegate.handleAppleEvent_withReplyEvent_(event, None)
    delegate.handleAppleEvent_withReplyEvent_(event, None)

    assert decisions == [True]


def test_install_sets_the_application_delegate() -> None:
    """Set NSApplication.shared's delegate to the installed login-launch delegate."""
    from AppKit import NSApplication

    macos_login_launch.install(lambda _is_login_launch: None)

    assert NSApplication.sharedApplication().delegate() is macos_login_launch._delegate
