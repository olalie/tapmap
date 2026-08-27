"""Application lifecycle coordination: shutdown signaling and the server thread.

request_shutdown() is the single entry point every shutdown trigger (signal,
UI action, or the server thread exiting unexpectedly) calls; only the main
thread, via wait_for_shutdown() returning, ever acts on it.
"""

from __future__ import annotations

import signal
import threading
from types import FrameType
from typing import Final

from werkzeug.serving import BaseWSGIServer

_WAIT_POLL_S: Final[float] = 0.5


class LifecycleCoordinator:
    """Coordinate shutdown requests across threads."""

    def __init__(self) -> None:
        self._shutdown_event = threading.Event()

    def request_shutdown(self) -> None:
        """Signal that the application should shut down. Safe from any thread, idempotent."""
        self._shutdown_event.set()

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
