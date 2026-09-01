"""Native SMAppService.mainApp status/register/unregister for macOS autostart."""

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
    """Raised when SMAppService.mainApp cannot be queried, registered, or unregistered.

    code holds the underlying NSError's numeric code when available, so
    callers can recognize specific documented failures (e.g. kSMErrorJobNotFound)
    without parsing error text.
    """

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
    """Return SMAppService.mainApp's current status.

    Raises:
        ServiceManagementError: the framework is unavailable, or the status is unrecognized.
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
    """Register TapMap with SMAppService.mainApp for login launch.

    Raises:
        ServiceManagementError: the framework is unavailable, or registration failed.
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
    """Unregister TapMap from SMAppService.mainApp.

    Raises:
        ServiceManagementError: the framework is unavailable, or unregistration failed.
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
