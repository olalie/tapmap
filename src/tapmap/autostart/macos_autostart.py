"""Manage TapMap autostart on macOS through SMAppService.mainApp."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

from tapmap.state.autostart import (
    AutostartDecision,
    MacosMainAppStatus,
    NativeMainAppStatus,
    WriteOutcome,
    decide_macos_autostart_display,
)

from . import macos_service_management as service_management
from . import marker

logger = logging.getLogger(__name__)

_UNQUERYABLE_STATUS: Final[NativeMainAppStatus] = NativeMainAppStatus(queryable=False, status=None)


def _query_native_status() -> NativeMainAppStatus:
    """Return the current SMAppService.mainApp registration status."""
    try:
        status = service_management.query_status()
    except service_management.ServiceManagementError:
        return _UNQUERYABLE_STATUS
    return NativeMainAppStatus(queryable=True, status=status)


def query_display_state(*, is_frozen: bool) -> AutostartDecision:
    """Return the state and action for the autostart control."""
    if not is_frozen:
        # Source runs must not query SMAppService.mainApp.
        return decide_macos_autostart_display(status=_UNQUERYABLE_STATUS, is_source_run=True)

    status = _query_native_status()
    return decide_macos_autostart_display(status=status, is_source_run=False)


def _register_and_confirm() -> tuple[WriteOutcome, str | None]:
    """Call register(), then query status once and interpret the result.

    Shared tail for create() and recover_and_enable(): both end with exactly
    this step, differing only in what happens before it.
    """
    try:
        service_management.register()
    except service_management.ServiceManagementError as exc:
        return WriteOutcome.ERROR, str(exc)

    try:
        status = service_management.query_status()
    except service_management.ServiceManagementError as exc:
        return WriteOutcome.ERROR, str(exc)

    if status in (MacosMainAppStatus.ENABLED, MacosMainAppStatus.REQUIRES_APPROVAL):
        return WriteOutcome.OK, None

    return (
        WriteOutcome.ERROR,
        f"SMAppService.mainApp status after register was {status.value}, activation not confirmed.",
    )


def create() -> tuple[WriteOutcome, str | None]:
    """Enable autostart from NOT_REGISTERED by registering with SMAppService.mainApp.

    Only reports success once the resulting status is confirmed enabled or
    pending user approval.
    """
    return _register_and_confirm()


def recover_and_enable() -> tuple[WriteOutcome, str | None]:
    """Recover from NOT_FOUND and enable autostart: one unregister-then-register attempt.

    The cleanup unregister() is best-effort: NOT_FOUND already means there is
    nothing registered to clear, so its failure is expected and does not
    abort recovery. register() and the resulting status query remain the
    sole authority on success. Never retries beyond this one attempt.
    """
    try:
        service_management.unregister()
    except service_management.ServiceManagementError as exc:
        logger.info("Cleanup unregister() before NOT_FOUND recovery failed: %s", exc)

    return _register_and_confirm()


def disable() -> tuple[WriteOutcome, str | None]:
    """Disable autostart by unregistering TapMap from SMAppService.mainApp.

    Only NOT_REGISTERED after unregister() is treated as confirmed success.
    Never re-registers on this path.
    """
    try:
        service_management.unregister()
    except service_management.ServiceManagementError as exc:
        return WriteOutcome.ERROR, str(exc)

    try:
        status = service_management.query_status()
    except service_management.ServiceManagementError as exc:
        return WriteOutcome.ERROR, str(exc)

    if status == MacosMainAppStatus.NOT_REGISTERED:
        return WriteOutcome.OK, None

    return (
        WriteOutcome.ERROR,
        f"SMAppService.mainApp status after unregister was {status.value}, not confirmed disabled.",
    )


def open_settings() -> None:
    """Open System Settings to the Login Items panel for the user to approve autostart."""
    try:
        service_management.open_system_settings_login_items()
    except Exception:
        logger.exception("Unable to open System Settings Login Items.")


def run_startup_setup(*, app_data_dir: Path, is_frozen: bool) -> None:
    """Set up autostart on first launch when needed.

    Failures are logged and must not prevent TapMap from starting.
    """
    if not is_frozen:
        return
    if marker.has_completed_setup(app_data_dir):
        return

    status = _query_native_status()

    if not status.queryable:
        logger.warning("Unable to query SMAppService.mainApp for initial autostart setup.")
        return

    if status.status in (MacosMainAppStatus.ENABLED, MacosMainAppStatus.REQUIRES_APPROVAL):
        # Already registered in some form; preserve it.
        marker.mark_setup_completed(app_data_dir)
        return

    if status.status == MacosMainAppStatus.NOT_REGISTERED:
        outcome, error = create()
    elif status.status == MacosMainAppStatus.NOT_FOUND:
        outcome, error = recover_and_enable()
    else:
        # Unrecognized status value: ambiguous, retry on a later launch.
        return

    if outcome == WriteOutcome.OK:
        marker.mark_setup_completed(app_data_dir)
    else:
        logger.warning("Unable to complete initial autostart registration: %s", error)
