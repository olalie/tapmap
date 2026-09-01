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
    """Register autostart and confirm the resulting status."""
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
    """Register autostart and confirm it is enabled or requires approval."""
    return _register_and_confirm()


def recover_and_enable() -> tuple[WriteOutcome, str | None]:
    """Recover autostart from NOT_FOUND.

    Ignore cleanup errors, then register once and confirm the resulting status.
    """
    try:
        service_management.unregister()
    except service_management.ServiceManagementError as exc:
        logger.info("Cleanup unregister() before NOT_FOUND recovery failed: %s", exc)

    return _register_and_confirm()


def disable() -> tuple[WriteOutcome, str | None]:
    """Unregister autostart and require NOT_REGISTERED to confirm success."""
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
    """Open the Login Items settings."""
    try:
        service_management.open_system_settings_login_items()
    except Exception:
        logger.exception("Unable to open System Settings Login Items.")


def run_startup_setup(*, app_data_dir: Path, is_frozen: bool) -> None:
    """Set up autostart on first launch without blocking TapMap startup on failure."""
    if not is_frozen:
        return
    if marker.has_completed_setup(app_data_dir):
        return

    status = _query_native_status()

    if not status.queryable:
        logger.warning("Unable to query SMAppService.mainApp for initial autostart setup.")
        return

    if status.status in (MacosMainAppStatus.ENABLED, MacosMainAppStatus.REQUIRES_APPROVAL):
        # Preserve existing registration.
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
