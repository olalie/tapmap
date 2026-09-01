"""Access SMAppService.mainApp for macOS autostart."""

from __future__ import annotations

from typing import Final

from tapmap.state.autostart import MacosMainAppStatus

# SMAppServiceStatus raw values, from Apple's ServiceManagement framework.
_STATUS_NOT_REGISTERED: Final[int] = 0
_STATUS_ENABLED: Final[int] = 1
_STATUS_REQUIRES_APPROVAL: Final[int] = 2
_STATUS_NOT_FOUND: Final[int] = 3

_STATUS_BY_RAW_VALUE: Final[dict[int, MacosMainAppStatus]] = {
    _STATUS_NOT_REGISTERED: MacosMainAppStatus.NOT_REGISTERED,
    _STATUS_ENABLED: MacosMainAppStatus.ENABLED,
    _STATUS_REQUIRES_APPROVAL: MacosMainAppStatus.REQUIRES_APPROVAL,
    _STATUS_NOT_FOUND: MacosMainAppStatus.NOT_FOUND,
}


class ServiceManagementError(Exception):
    """Represent an SMAppService failure with its NSError code when available."""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


def _main_app():
    """Return SMAppService.mainApp."""
    from ServiceManagement import SMAppService

    return SMAppService.mainAppService()


def _raw_status() -> int:
    """Return the raw SMAppServiceStatus integer for SMAppService.mainApp."""
    return _main_app().status()


def query_status() -> MacosMainAppStatus:
    """Return the current SMAppService.mainApp status.

    Raises:
        ServiceManagementError: If the status cannot be read or recognized.
    """
    try:
        raw_status = _raw_status()
    except Exception as exc:
        raise ServiceManagementError(str(exc)) from exc

    try:
        return _STATUS_BY_RAW_VALUE[raw_status]
    except KeyError as exc:
        raise ServiceManagementError(f"Unrecognized SMAppService status: {raw_status!r}") from exc


def register() -> None:
    """Register TapMap for login launch.

    Raises:
        ServiceManagementError: If registration fails.
    """
    try:
        ok, error = _main_app().registerAndReturnError_(None)
    except Exception as exc:
        raise ServiceManagementError(str(exc)) from exc
    if not ok:
        raise ServiceManagementError(
            str(error) if error is not None else "register() failed",
            code=error.code() if error is not None else None,
        )


def unregister() -> None:
    """Unregister TapMap from login launch.

    Raises:
        ServiceManagementError: If unregistration fails.
    """
    try:
        ok, error = _main_app().unregisterAndReturnError_(None)
    except Exception as exc:
        raise ServiceManagementError(str(exc)) from exc
    if not ok:
        raise ServiceManagementError(
            str(error) if error is not None else "unregister() failed",
            code=error.code() if error is not None else None,
        )


def open_system_settings_login_items() -> None:
    """Open System Settings to the Login Items panel."""
    from ServiceManagement import SMAppService

    SMAppService.openSystemSettingsLoginItems()
