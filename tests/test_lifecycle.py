"""Test shutdown coordination and server lifecycle."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from tapmap import lifecycle
from tapmap.lifecycle import LifecycleCoordinator, start_server_thread


def test_request_shutdown_unblocks_wait_for_shutdown() -> None:
    """Unblock a shutdown wait when shutdown is requested."""
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


def test_request_shutdown_stops_a_registered_tray_icon() -> None:
    """Stop the tray icon when shutdown is requested."""
    coordinator = LifecycleCoordinator()

    class _FakeIcon:
        def __init__(self) -> None:
            self.stopped = False

        def stop(self) -> None:
            self.stopped = True

    icon = _FakeIcon()
    coordinator.set_tray_icon(icon)

    coordinator.request_shutdown()

    assert icon.stopped is True


def test_run_tray_honors_a_shutdown_already_requested_before_the_icon_started() -> None:
    """Handle shutdown requested before the tray starts.

    pystray ignores stop() before the icon is running. Recheck shutdown after
    startup so the process can still exit.
    """
    coordinator = LifecycleCoordinator()

    class _FakeIcon:
        """Simulate pystray ignoring stop() before run()."""

        def __init__(self) -> None:
            self._running = False
            self._stopped_event = threading.Event()

        def stop(self) -> None:
            if self._running:
                self._stopped_event.set()

        def run(self, setup=None) -> None:
            self._running = True
            if setup is not None:
                setup(self)
            self._stopped_event.wait()

    icon = _FakeIcon()
    coordinator.set_tray_icon(icon)
    coordinator.request_shutdown()  # arrives before the icon is running

    finished = threading.Event()

    def _run() -> None:
        coordinator.run_tray(icon)
        finished.set()

    runner = threading.Thread(target=_run, daemon=True)
    runner.start()
    runner.join(timeout=2)

    assert finished.is_set()


def test_run_tray_always_stops_the_windows_message_loop_nudge(monkeypatch) -> None:
    """Stop the Windows message-loop timer when the tray exits.

    The timer lets Windows process Ctrl+C and SIGTERM while pystray is blocked
    in GetMessage().
    """
    coordinator = LifecycleCoordinator()
    calls: list[object] = []

    monkeypatch.setattr(
        lifecycle, "_start_windows_message_loop_nudge", lambda: calls.append("start") or 42
    )
    monkeypatch.setattr(
        lifecycle,
        "_stop_windows_message_loop_nudge",
        lambda timer_id: calls.append(("stop", timer_id)),
    )

    class _FakeIcon:
        def run(self, setup=None) -> None:
            calls.append("run")
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        coordinator.run_tray(_FakeIcon())

    assert calls == ["start", "run", ("stop", 42)]


def test_start_windows_message_loop_nudge_is_a_noop_off_windows(monkeypatch) -> None:
    """Do not start the message-loop timer outside Windows."""
    monkeypatch.setattr(lifecycle.platform, "system", lambda: "Linux")

    assert lifecycle._start_windows_message_loop_nudge() is None


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only Ctrl+C nudge timer")
def test_start_windows_message_loop_nudge_returns_none_when_settimer_fails(monkeypatch) -> None:
    """Return no timer when SetTimer() fails."""
    monkeypatch.setattr(lifecycle.ctypes.windll.user32, "SetTimer", lambda *args: 0)

    assert lifecycle._start_windows_message_loop_nudge() is None


def test_wait_for_shutdown_is_interruptible_by_a_real_signal_on_the_main_thread() -> None:
    """Handle a real SIGINT while waiting for shutdown."""
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

    # Give the subprocess the same source import path used by pytest.
    src_dir = str(Path(__file__).resolve().parent.parent / "src")
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        os.pathsep.join([src_dir, existing_pythonpath]) if existing_pythonpath else src_dir
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=5,
        env=env,
    )

    assert "SHUTDOWN_REQUESTED" in result.stdout


def test_start_server_thread_requests_shutdown_when_serve_forever_returns() -> None:
    """Request shutdown when the server stops normally."""
    coordinator = LifecycleCoordinator()

    class _FakeServer:
        def serve_forever(self) -> None:
            return

    thread = start_server_thread(_FakeServer(), coordinator)
    thread.join(timeout=2)

    assert not thread.is_alive()
    coordinator.wait_for_shutdown()


def test_start_server_thread_requests_shutdown_when_serve_forever_raises(monkeypatch) -> None:
    """Request shutdown when the server raises an exception."""
    monkeypatch.setattr(threading, "excepthook", lambda args: None)
    coordinator = LifecycleCoordinator()

    class _FakeServer:
        def serve_forever(self) -> None:
            raise RuntimeError("boom")

    thread = start_server_thread(_FakeServer(), coordinator)
    thread.join(timeout=2)

    assert not thread.is_alive()
    coordinator.wait_for_shutdown()
