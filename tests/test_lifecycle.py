"""Test shutdown coordination and the server thread wrapper."""

from __future__ import annotations

import subprocess
import sys
import textwrap
import threading

from tapmap.lifecycle import LifecycleCoordinator, start_server_thread


def test_request_shutdown_unblocks_wait_for_shutdown() -> None:
    """A thread blocked in wait_for_shutdown() unblocks once request_shutdown() is called."""
    coordinator = LifecycleCoordinator()
    unblocked = threading.Event()

    def _wait() -> None:
        coordinator.wait_for_shutdown()
        unblocked.set()

    waiter = threading.Thread(target=_wait, daemon=True)
    waiter.start()
    assert not unblocked.wait(timeout=0.2)

    coordinator.request_shutdown()
    waiter.join(timeout=2)
    assert unblocked.is_set()


def test_wait_for_shutdown_is_interruptible_by_a_real_signal_on_the_main_thread() -> None:
    """Regression test: wait_for_shutdown() must react to a real Ctrl+C (SIGINT)."""
    # Must run as a real subprocess, not an in-process thread: CPython only
    # dispatches signal handlers on a process's actual main thread, so a
    # background thread standing in for it would not exercise this at all.
    script = textwrap.dedent(
        """
        import signal
        import threading
        import time

        from tapmap.lifecycle import LifecycleCoordinator

        coordinator = LifecycleCoordinator()
        coordinator.install_signal_handlers()

        def _raise_sigint_soon():
            time.sleep(0.3)
            signal.raise_signal(signal.SIGINT)

        threading.Thread(target=_raise_sigint_soon, daemon=True).start()
        coordinator.wait_for_shutdown()
        print("SHUTDOWN_REQUESTED")
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert "SHUTDOWN_REQUESTED" in result.stdout


def test_start_server_thread_requests_shutdown_when_serve_forever_returns() -> None:
    """Shutdown is requested once serve_forever() exits normally."""
    coordinator = LifecycleCoordinator()

    class _FakeServer:
        def serve_forever(self) -> None:
            return

    thread = start_server_thread(_FakeServer(), coordinator)
    thread.join(timeout=2)

    assert not thread.is_alive()
    coordinator.wait_for_shutdown()


def test_start_server_thread_requests_shutdown_when_serve_forever_raises(monkeypatch) -> None:
    """Shutdown is requested even when serve_forever() exits via an unhandled exception."""
    monkeypatch.setattr(threading, "excepthook", lambda args: None)
    coordinator = LifecycleCoordinator()

    class _FakeServer:
        def serve_forever(self) -> None:
            raise RuntimeError("boom")

    thread = start_server_thread(_FakeServer(), coordinator)
    thread.join(timeout=2)

    assert not thread.is_alive()
    coordinator.wait_for_shutdown()
