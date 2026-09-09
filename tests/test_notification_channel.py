"""Tests for the notification channel dispatcher."""

from __future__ import annotations

import logging
from typing import Any

from tapmap.notifications.channel import dispatch_notification


class _RecordingChannel:
    """Record events sent to the channel."""

    def __init__(self) -> None:
        self.received: list[dict[str, Any]] = []

    def send(self, event: dict[str, Any]) -> None:
        self.received.append(event)


class _FailingChannel:
    """Raise on every send."""

    def send(self, event: dict[str, Any]) -> None:
        raise RuntimeError("channel unavailable")


def test_empty_channel_list_is_a_no_op() -> None:
    dispatch_notification({"ip": "8.8.8.8"}, [])


def test_event_is_delivered_to_every_channel() -> None:
    a, b = _RecordingChannel(), _RecordingChannel()
    event = {"ip": "8.8.8.8"}

    dispatch_notification(event, [a, b])

    assert a.received == [event]
    assert b.received == [event]


def test_one_channel_failing_does_not_prevent_another() -> None:
    recorder = _RecordingChannel()
    event = {"ip": "8.8.8.8"}

    dispatch_notification(event, [_FailingChannel(), recorder])

    assert recorder.received == [event]


def test_channel_failure_is_logged_and_not_raised(caplog: Any) -> None:
    with caplog.at_level(logging.ERROR, logger="tapmap.notifications.channel"):
        dispatch_notification({"ip": "8.8.8.8"}, [_FailingChannel()])

    assert "Notification channel failed" in caplog.text
