"""Show native OS desktop notifications for Significant Connection events."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

APP_NAME = "TapMap"
# Shared reverse-DNS identity, matching the macOS bundle identifier and the
# Linux desktop file (no.tip.tapmap / no.tip.tapmap.desktop).
WINDOWS_AUMID = "no.tip.tapmap"
LINUX_ICON_NAME = "tapmap"

_REASON_LABELS = {
    "new_app": "New application",
    "new_country": "New country",
    "new_provider": "New network operator",
    "new_port": "New port",
    "verification_failed": "Verification failed",
}


class DesktopNotificationChannel:
    """Show a native OS notification for each Significant Connection event, when enabled."""

    def __init__(self, sender: Callable[[dict[str, Any]], None], *, enabled: bool) -> None:
        self._sender = sender
        self.enabled = enabled

    def send(self, event: dict[str, Any]) -> None:
        """Show a native notification for one Significant Connection event, if enabled."""
        if not self.enabled:
            return
        self._sender(event)


def create_desktop_notification_channel(
    *, icon_path: Path, enabled: bool
) -> DesktopNotificationChannel | None:
    """Build the desktop notification channel for the current OS, or None if unsupported."""
    if sys.platform == "win32":
        sender = _build_windows_sender(icon_path)
    elif sys.platform == "linux":
        sender = _build_linux_sender()
    elif sys.platform == "darwin":
        # UNUserNotificationCenter behavior under TapMap's LSUIElement=True
        # bundle has not yet been validated against a signed build, so no
        # sender is implemented here pending that test.
        logger.info("Desktop notifications are not yet implemented for this platform.")
        return None
    else:
        logger.info("Desktop notifications are not supported on this platform.")
        return None

    if sender is None:
        return None

    return DesktopNotificationChannel(sender, enabled=enabled)


def _format_reasons(reasons: Any) -> str:
    """Join an event's significance reasons into one comma-separated, user-facing line."""
    values = reasons if isinstance(reasons, list) else []
    return ", ".join(_REASON_LABELS.get(r, str(r)) for r in values)


def _notification_text(event: dict[str, Any]) -> tuple[str, str]:
    """Build a (title, body) pair describing one Significant Connection event."""
    app_name = event.get("app_name") or "Unknown application"
    reasons = _format_reasons(event.get("reasons"))
    country = event.get("country") or "an unknown location"
    return reasons, f"{app_name} — {country}"


def _build_windows_sender(icon_path: Path) -> Callable[[dict[str, Any]], None] | None:
    """Build a Windows toast sender via windows-toasts, or None if unavailable."""
    try:
        import ctypes

        from windows_toasts import Toast, ToastDisplayImage, WindowsToaster
    except ImportError:
        logger.warning("windows-toasts is not installed; desktop notifications are unavailable.")
        return None

    # Classic (unpackaged) Win32 apps show under a generic identity/icon
    # unless the process claims an explicit AppUserModelID matching the one
    # registered on the Start Menu shortcut (see tools/windows/TapMap.iss).
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_AUMID)
    except OSError:
        logger.warning("Unable to set the Windows AppUserModelID.", exc_info=True)

    toaster = WindowsToaster(APP_NAME)
    display_image = ToastDisplayImage.fromPath(str(icon_path)) if icon_path.exists() else None

    def send(event: dict[str, Any]) -> None:
        title, body = _notification_text(event)
        toast = Toast()
        toast.text_fields = [title, body]
        if display_image is not None:
            toast.AddImage(display_image)
        toaster.show_toast(toast)

    return send


def _build_linux_sender() -> Callable[[dict[str, Any]], None] | None:
    """Build a Linux notification sender via libnotify (GObject introspection)."""
    try:
        import gi

        gi.require_version("Notify", "0.7")
        from gi.repository import Notify
    except (ImportError, ValueError):
        # gi.require_version() raises ValueError when the Notify typelib is missing.
        logger.warning(
            "libnotify GObject bindings are unavailable; desktop notifications are unavailable."
        )
        return None

    if not Notify.is_initted():
        Notify.init(APP_NAME)

    def send(event: dict[str, Any]) -> None:
        # One blocking D-Bus call; needs no GLib main loop, so this is safe to
        # call from the Werkzeug worker thread.
        title, body = _notification_text(event)
        Notify.Notification.new(title, body, LINUX_ICON_NAME).show()

    return send
