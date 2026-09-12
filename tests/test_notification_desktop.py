"""Tests for the desktop notification channel."""

from __future__ import annotations

import ctypes
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

from tapmap.notifications.desktop import (
    DesktopNotificationChannel,
    _format_reasons,
    _notification_text,
    create_desktop_notification_channel,
)


def _event(**overrides: object) -> dict[str, Any]:
    values: dict[str, object] = {
        "timestamp": "2026-09-08T12:00:00",
        "reasons": ["new_country"],
        "app_name": "Firefox",
        "country": "United States",
    }
    values.update(overrides)
    return values


# --- DesktopNotificationChannel: enabled gating ---


def test_disabled_channel_does_not_call_sender() -> None:
    calls: list[dict[str, Any]] = []
    channel = DesktopNotificationChannel(calls.append, enabled=False)

    channel.send(_event())

    assert calls == []


def test_enabled_channel_calls_sender() -> None:
    calls: list[dict[str, Any]] = []
    channel = DesktopNotificationChannel(calls.append, enabled=True)
    event = _event()

    channel.send(event)

    assert calls == [event]


def test_enabled_flag_can_be_toggled_at_runtime() -> None:
    calls: list[dict[str, Any]] = []
    channel = DesktopNotificationChannel(calls.append, enabled=True)

    channel.enabled = False
    channel.send(_event())

    assert calls == []


def test_activate_is_a_noop_without_an_on_activate_callback() -> None:
    channel = DesktopNotificationChannel(lambda _event: None, enabled=True)

    channel.activate()  # must not raise


def test_activate_calls_the_on_activate_callback() -> None:
    calls: list[None] = []
    channel = DesktopNotificationChannel(
        lambda _event: None, enabled=True, on_activate=lambda: calls.append(None)
    )

    channel.activate()

    assert calls == [None]


# --- notification text formatting ---


def test_format_reasons_maps_known_reasons_to_labels() -> None:
    assert _format_reasons(["new_country", "new_app"]) == "New country, New application"


def test_format_reasons_falls_back_to_raw_value_for_unknown_reason() -> None:
    assert _format_reasons(["something_else"]) == "something_else"


def test_format_reasons_handles_non_list_input() -> None:
    assert _format_reasons(None) == ""


def test_notification_text_includes_app_name_and_country() -> None:
    title, body = _notification_text(_event(app_name="Firefox", country="Germany"))

    assert "Firefox" not in title
    assert "New country" in title
    assert "Firefox" in body
    assert "Germany" in body


def test_notification_text_falls_back_for_missing_app_name_and_country() -> None:
    _title, body = _notification_text(_event(app_name=None, country=None))

    assert "Unknown application" in body
    assert "an unknown location" in body


# --- create_desktop_notification_channel: unsupported platform ---


def test_other_platform_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(sys, "platform", "freebsd13")

    with caplog.at_level(logging.INFO, logger="tapmap.notifications.desktop"):
        result = create_desktop_notification_channel(
            icon_path=tmp_path / "tapmap.ico", enabled=True
        )

    assert result is None
    assert "not supported" in caplog.text


# --- Windows sender ---


class _FakeToast:
    def __init__(self) -> None:
        self.text_fields: list[str] = []
        self.images: list[Any] = []

    def AddImage(self, image: Any) -> None:
        self.images.append(image)


class _FakeWindowsToaster:
    instances: ClassVar[list[_FakeWindowsToaster]] = []

    def __init__(self, application_text: str) -> None:
        self.application_text = application_text
        self.shown: list[_FakeToast] = []
        _FakeWindowsToaster.instances.append(self)

    def show_toast(self, toast: _FakeToast) -> None:
        self.shown.append(toast)


class _FakeToastDisplayImage:
    def __init__(self, path: str) -> None:
        self.path = path

    @classmethod
    def fromPath(cls, path: str) -> _FakeToastDisplayImage:
        return cls(path)


def _install_fake_windows_toasts(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    _FakeWindowsToaster.instances = []
    fake_module = SimpleNamespace(
        Toast=_FakeToast,
        ToastDisplayImage=_FakeToastDisplayImage,
        WindowsToaster=_FakeWindowsToaster,
    )
    monkeypatch.setitem(sys.modules, "windows_toasts", fake_module)
    return fake_module


def _install_fake_windll(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    calls: list[str] = []
    fake_shell32 = SimpleNamespace(
        SetCurrentProcessExplicitAppUserModelID=lambda aumid: calls.append(aumid)
    )
    fake_windll = SimpleNamespace(shell32=fake_shell32)
    monkeypatch.setattr(ctypes, "windll", fake_windll, raising=False)
    return SimpleNamespace(calls=calls)


def test_windows_missing_dependency_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "windows_toasts", None)

    with caplog.at_level(logging.WARNING, logger="tapmap.notifications.desktop"):
        result = create_desktop_notification_channel(
            icon_path=tmp_path / "tapmap.ico", enabled=True
        )

    assert result is None
    assert "windows-toasts is not installed" in caplog.text


def test_windows_sender_sets_app_user_model_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    _install_fake_windows_toasts(monkeypatch)
    windll = _install_fake_windll(monkeypatch)

    channel = create_desktop_notification_channel(icon_path=tmp_path / "tapmap.ico", enabled=True)

    assert channel is not None
    assert windll.calls == ["no.tip.tapmap"]


def test_windows_sender_shows_toast_with_expected_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    _install_fake_windows_toasts(monkeypatch)
    _install_fake_windll(monkeypatch)

    channel = create_desktop_notification_channel(icon_path=tmp_path / "tapmap.ico", enabled=True)
    assert channel is not None
    event = _event()

    channel.send(event)

    toaster = _FakeWindowsToaster.instances[-1]
    assert toaster.application_text == "TapMap"
    assert len(toaster.shown) == 1
    assert toaster.shown[0].text_fields == list(_notification_text(event))


def test_windows_sender_adds_image_when_icon_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    _install_fake_windows_toasts(monkeypatch)
    _install_fake_windll(monkeypatch)
    icon_path = tmp_path / "tapmap.ico"
    icon_path.write_bytes(b"")

    channel = create_desktop_notification_channel(icon_path=icon_path, enabled=True)
    assert channel is not None
    channel.send(_event())

    fake_module = sys.modules["windows_toasts"]
    toaster = fake_module.WindowsToaster.instances[-1]  # type: ignore[attr-defined]
    assert len(toaster.shown) == 1
    assert len(toaster.shown[0].images) == 1


def test_windows_sender_skips_image_when_icon_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    _install_fake_windows_toasts(monkeypatch)
    _install_fake_windll(monkeypatch)

    channel = create_desktop_notification_channel(
        icon_path=tmp_path / "does_not_exist.ico", enabled=True
    )
    assert channel is not None
    channel.send(_event())

    fake_module = sys.modules["windows_toasts"]
    toaster = fake_module.WindowsToaster.instances[-1]  # type: ignore[attr-defined]
    assert toaster.shown[0].images == []


# --- Linux sender ---


class _FakeNotification:
    def __init__(self, title: str, body: str, icon_name: str) -> None:
        self.title = title
        self.body = body
        self.icon_name = icon_name
        self.shown = False

    def show(self) -> None:
        self.shown = True


def _install_fake_gi(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    created: list[_FakeNotification] = []

    class _FakeNotify:
        _initted = False
        init_calls: ClassVar[list[str]] = []

        @classmethod
        def is_initted(cls) -> bool:
            return cls._initted

        @classmethod
        def init(cls, app_name: str) -> None:
            cls._initted = True
            cls.init_calls.append(app_name)

        class Notification:
            @staticmethod
            def new(title: str, body: str, icon_name: str) -> _FakeNotification:
                notification = _FakeNotification(title, body, icon_name)
                created.append(notification)
                return notification

    fake_gi = SimpleNamespace(require_version=lambda *_args, **_kwargs: None)
    fake_gi_repository = SimpleNamespace(Notify=_FakeNotify)
    monkeypatch.setitem(sys.modules, "gi", fake_gi)
    monkeypatch.setitem(sys.modules, "gi.repository", fake_gi_repository)
    return SimpleNamespace(notify=_FakeNotify, created=created)


def test_linux_missing_dependency_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setitem(sys.modules, "gi", None)

    with caplog.at_level(logging.WARNING, logger="tapmap.notifications.desktop"):
        result = create_desktop_notification_channel(
            icon_path=tmp_path / "tapmap.ico", enabled=True
        )

    assert result is None
    assert "libnotify" in caplog.text


def test_linux_sender_initializes_notify_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    fake = _install_fake_gi(monkeypatch)

    channel = create_desktop_notification_channel(icon_path=tmp_path / "tapmap.ico", enabled=True)
    assert channel is not None
    channel.send(_event())
    channel.send(_event())

    assert fake.notify.init_calls == ["TapMap"]


def test_linux_sender_shows_notification_with_expected_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    fake = _install_fake_gi(monkeypatch)

    channel = create_desktop_notification_channel(icon_path=tmp_path / "tapmap.ico", enabled=True)
    assert channel is not None
    event = _event(app_name="Firefox", country="Germany", reasons=["new_country"])

    channel.send(event)

    assert len(fake.created) == 1
    notification = fake.created[0]
    assert "New country" in notification.title
    assert "Firefox" in notification.body
    assert "Germany" in notification.body
    assert notification.icon_name == "tapmap"
    assert notification.shown is True


# --- macOS sender ---


_FAKE_DEFAULT_SOUND = object()


class _FakeMutableNotificationContent:
    def __init__(self) -> None:
        self.title: str | None = None
        self.body: str | None = None
        self.sound: Any = None

    def init(self) -> _FakeMutableNotificationContent:
        return self

    def setTitle_(self, title: str) -> None:
        self.title = title

    def setBody_(self, body: str) -> None:
        self.body = body

    def setSound_(self, sound: Any) -> None:
        self.sound = sound


class _FakeNotificationRequest:
    def __init__(
        self, identifier: str, content: _FakeMutableNotificationContent, trigger: Any
    ) -> None:
        self.identifier = identifier
        self.content = content
        self.trigger = trigger


class _FakeUserNotificationCenter:
    def __init__(self) -> None:
        self.authorization_options: list[int] = []
        self.added_requests: list[_FakeNotificationRequest] = []
        self.grant_authorization = True
        self.authorization_error: str | None = None
        self.delivery_error: str | None = None

    def requestAuthorizationWithOptions_completionHandler_(
        self, options: int, completion: Any
    ) -> None:
        self.authorization_options.append(options)
        completion(self.grant_authorization, self.authorization_error)

    def addNotificationRequest_withCompletionHandler_(
        self, request: _FakeNotificationRequest, completion: Any
    ) -> None:
        self.added_requests.append(request)
        completion(self.delivery_error)


def _install_fake_user_notifications(
    monkeypatch: pytest.MonkeyPatch,
) -> _FakeUserNotificationCenter:
    center = _FakeUserNotificationCenter()
    fake_module = SimpleNamespace(
        UNUserNotificationCenter=SimpleNamespace(currentNotificationCenter=lambda: center),
        UNMutableNotificationContent=SimpleNamespace(alloc=_FakeMutableNotificationContent),
        UNNotificationRequest=SimpleNamespace(
            requestWithIdentifier_content_trigger_=_FakeNotificationRequest
        ),
        UNNotificationSound=SimpleNamespace(defaultSound=lambda: _FAKE_DEFAULT_SOUND),
        UNAuthorizationOptionAlert=1 << 2,
        UNAuthorizationOptionSound=1 << 1,
    )
    monkeypatch.setitem(sys.modules, "UserNotifications", fake_module)
    return center


def test_macos_missing_dependency_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "UserNotifications", None)

    with caplog.at_level(logging.WARNING, logger="tapmap.notifications.desktop"):
        result = create_desktop_notification_channel(
            icon_path=tmp_path / "tapmap.ico", enabled=True
        )

    assert result is None
    assert "pyobjc-framework-UserNotifications" in caplog.text


def test_macos_sender_does_not_request_authorization_before_activate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    center = _install_fake_user_notifications(monkeypatch)

    channel = create_desktop_notification_channel(icon_path=tmp_path / "tapmap.ico", enabled=True)

    assert channel is not None
    assert center.authorization_options == []


def test_macos_sender_requests_authorization_on_activate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    center = _install_fake_user_notifications(monkeypatch)

    channel = create_desktop_notification_channel(icon_path=tmp_path / "tapmap.ico", enabled=True)
    assert channel is not None

    channel.activate()

    assert center.authorization_options == [(1 << 2) | (1 << 1)]


def test_macos_sender_shows_notification_with_expected_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    center = _install_fake_user_notifications(monkeypatch)

    channel = create_desktop_notification_channel(icon_path=tmp_path / "tapmap.ico", enabled=True)
    assert channel is not None
    channel.activate()
    event = _event(app_name="Firefox", country="Germany", reasons=["new_country"])

    channel.send(event)

    assert len(center.added_requests) == 1
    request = center.added_requests[0]
    assert request.content.title == "New country"
    assert "Firefox" in request.content.body
    assert "Germany" in request.content.body
    assert request.identifier


def test_macos_sender_uses_the_default_notification_sound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    center = _install_fake_user_notifications(monkeypatch)

    channel = create_desktop_notification_channel(icon_path=tmp_path / "tapmap.ico", enabled=True)
    assert channel is not None
    channel.activate()

    channel.send(_event())

    assert center.added_requests[0].content.sound is _FAKE_DEFAULT_SOUND


def test_macos_sender_uses_a_distinct_identifier_per_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    center = _install_fake_user_notifications(monkeypatch)

    channel = create_desktop_notification_channel(icon_path=tmp_path / "tapmap.ico", enabled=True)
    assert channel is not None
    channel.activate()

    channel.send(_event())
    channel.send(_event())

    identifiers = [request.identifier for request in center.added_requests]
    assert len(set(identifiers)) == 2


def test_macos_sender_attempts_delivery_before_activation_is_called(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """send() does not depend on activate() having run first."""
    monkeypatch.setattr(sys, "platform", "darwin")
    center = _install_fake_user_notifications(monkeypatch)

    channel = create_desktop_notification_channel(icon_path=tmp_path / "tapmap.ico", enabled=True)
    assert channel is not None

    channel.send(_event())

    assert len(center.added_requests) == 1


def test_macos_sender_still_attempts_delivery_after_authorization_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Do not cache the denied result: macOS alone decides whether delivery succeeds.

    A user who denies authorization and later enables it in System Settings
    must receive notifications without restarting TapMap.
    """
    monkeypatch.setattr(sys, "platform", "darwin")
    center = _install_fake_user_notifications(monkeypatch)
    center.grant_authorization = False

    channel = create_desktop_notification_channel(icon_path=tmp_path / "tapmap.ico", enabled=True)
    assert channel is not None
    channel.activate()

    channel.send(_event())

    assert len(center.added_requests) == 1


def test_macos_sender_logs_when_authorization_is_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    center = _install_fake_user_notifications(monkeypatch)
    center.grant_authorization = False
    center.authorization_error = "Notifications are not allowed for this application"

    channel = create_desktop_notification_channel(icon_path=tmp_path / "tapmap.ico", enabled=True)
    assert channel is not None

    with caplog.at_level(logging.INFO, logger="tapmap.notifications.desktop"):
        channel.activate()

    assert "not granted" in caplog.text


def test_macos_sender_logs_delivery_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    center = _install_fake_user_notifications(monkeypatch)
    center.delivery_error = "boom"

    channel = create_desktop_notification_channel(icon_path=tmp_path / "tapmap.ico", enabled=True)
    assert channel is not None
    channel.activate()

    with caplog.at_level(logging.WARNING, logger="tapmap.notifications.desktop"):
        channel.send(_event())

    assert "Failed to deliver" in caplog.text


# --- failure isolation through the real dispatcher ---


def test_send_failure_is_caught_by_dispatch_notification() -> None:
    from tapmap.notifications.channel import dispatch_notification

    def _raise(_event: dict[str, Any]) -> None:
        raise RuntimeError("notification backend unavailable")

    channel = DesktopNotificationChannel(_raise, enabled=True)

    dispatch_notification(_event(), [channel])
