"""Application lifecycle coordination: shutdown signaling and the server thread.

request_shutdown() is the single entry point every shutdown trigger (signal,
UI action, or the server thread exiting unexpectedly) calls; only the main
thread, via wait_for_shutdown() returning, ever acts on it.
"""

from __future__ import annotations

import ctypes
import logging
import platform
import signal
import threading
from types import FrameType
from typing import TYPE_CHECKING, Final

from werkzeug.serving import BaseWSGIServer

if TYPE_CHECKING:
    from pystray import Icon

logger = logging.getLogger(__name__)

_WAIT_POLL_S: Final[float] = 0.5


class LifecycleCoordinator:
    """Coordinate shutdown requests across threads."""

    def __init__(self) -> None:
        self._shutdown_event = threading.Event()
        self._icon: Icon | None = None

    def set_tray_icon(self, icon: Icon) -> None:
        """Register the running tray icon so request_shutdown() can also stop it."""
        self._icon = icon

    def request_shutdown(self) -> None:
        """Signal that the application should shut down. Safe from any thread, idempotent."""
        self._shutdown_event.set()
        if self._icon is not None:
            self._icon.stop()

    def run_tray(self, icon: Icon) -> None:
        """Run icon's blocking loop, honoring a shutdown already requested before it started.

        pystray's Icon.stop() has no effect until the icon is actually
        running, so a shutdown requested between set_tray_icon() and this
        call (e.g. the server thread dying immediately) would otherwise be
        lost, and icon.run() would then block forever. pystray only invokes
        the setup callback once it has marked the icon running, so
        re-checking and re-stopping there closes that window.
        """

        def _setup(icon: Icon) -> None:
            icon.visible = True
            if self._shutdown_event.is_set():
                icon.stop()

        timer_id = _start_windows_message_loop_nudge()
        try:
            icon.run(setup=_setup)
        finally:
            _stop_windows_message_loop_nudge(timer_id)

    def wait_for_shutdown(self) -> None:
        """Block the calling thread until shutdown has been requested."""
        # Poll instead of blocking indefinitely: on Windows, an unbounded wait
        # never returns to the interpreter loop, so a pending Ctrl+C handler
        # never runs.
        while not self._shutdown_event.wait(timeout=_WAIT_POLL_S):
            pass

    def install_signal_handlers(self) -> None:
        """Register SIGINT/SIGTERM handlers that request shutdown."""

        def _handle_signal(signum: int, frame: FrameType | None) -> None:
            self.request_shutdown()

        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)


def _start_windows_message_loop_nudge() -> int | None:
    """Start a periodic Windows timer that wakes pystray's blocking message loop, or None."""
    # pystray's Windows backend blocks in a plain GetMessage() call with no
    # timeout, which only returns when a real window message arrives - so a
    # pending Ctrl+C/SIGTERM sits undispatched until something unrelated
    # happens to wake it. A NULL-window timer posts WM_TIMER straight to the
    # calling (main) thread's own queue at a fixed interval, which
    # GetMessage() picks up like any other message - no pystray internals needed.
    if platform.system() != "Windows":
        return None

    timer_id = ctypes.windll.user32.SetTimer(0, 0, int(_WAIT_POLL_S * 1000), None)
    if timer_id == 0:
        logger.warning("Unable to create the Windows Ctrl+C responsiveness timer.")
        return None
    return timer_id


def _stop_windows_message_loop_nudge(timer_id: int | None) -> None:
    """Remove the timer started by _start_windows_message_loop_nudge(), if one was created."""
    if timer_id is not None:
        ctypes.windll.user32.KillTimer(0, timer_id)


def start_server_thread(
    server: BaseWSGIServer, coordinator: LifecycleCoordinator
) -> threading.Thread:
    """Run server.serve_forever() on a background thread; request shutdown when it exits."""

    def _serve() -> None:
        try:
            server.serve_forever()
        finally:
            coordinator.request_shutdown()

    # daemon=True is only a backstop for an unplanned main-thread failure -
    # the normal shutdown path always joins this thread before proceeding.
    thread = threading.Thread(target=_serve, daemon=True, name="tapmap-server")
    thread.start()
    return thread
