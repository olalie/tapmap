"""Detect macOS login-item launches from the kAEOpenApplication event.

The keyAELaunchedAsLogInItem ('lgit') value distinguishes login-item
launches from manual launches.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Final

import objc
from AppKit import NSApplication
from Foundation import NSAppleEventManager, NSObject

logger = logging.getLogger(__name__)

# PyObjC does not export these Apple Event FourCharCode constants.
_K_CORE_EVENT_CLASS: Final[int] = 0x61657674  # 'aevt'
_K_AE_OPEN_APPLICATION: Final[int] = 0x6F617070  # 'oapp'
_KEY_AE_PROP_DATA: Final[int] = 0x70726474  # 'prdt'
_KEY_AE_LAUNCHED_AS_LOGIN_ITEM: Final[int] = 0x6C676974  # 'lgit'

# NSApplication does not retain its delegate.
_delegate: _LoginLaunchDelegate | None = None


class _LoginLaunchDelegate(NSObject):
    """Report the macOS login-launch decision once."""

    def initWithCallback_(self, callback: Callable[[bool], None]) -> _LoginLaunchDelegate | None:
        """Store the launch-decision callback."""
        self = objc.super(_LoginLaunchDelegate, self).init()
        if self is None:
            return None
        self._callback = callback
        self._decided = False
        return self

    def applicationWillFinishLaunching_(self, notification: object) -> None:
        """Register the kAEOpenApplication handler before AppKit's default handling."""
        NSAppleEventManager.sharedAppleEventManager().setEventHandler_andSelector_forEventClass_andEventID_(
            self,
            "handleAppleEvent:withReplyEvent:",
            _K_CORE_EVENT_CLASS,
            _K_AE_OPEN_APPLICATION,
        )

    def handleAppleEvent_withReplyEvent_(self, event: object, reply: object) -> None:
        """Report whether the launch event marks a login-item launch."""
        if self._decided:
            return
        self._decided = True

        is_login_launch = False
        prop_data = event.paramDescriptorForKeyword_(_KEY_AE_PROP_DATA)
        if prop_data is not None:
            is_login_launch = prop_data.enumCodeValue() == _KEY_AE_LAUNCHED_AS_LOGIN_ITEM

        try:
            self._callback(is_login_launch)
        except Exception:
            logger.exception("macOS login-launch callback failed.")


def install(on_decision: Callable[[bool], None]) -> None:
    """Install login-launch detection before NSApplication.run() starts.

    Call on_decision once on the main thread with the detected launch type.
    """
    global _delegate
    app = NSApplication.sharedApplication()
    _delegate = _LoginLaunchDelegate.alloc().initWithCallback_(on_decision)
    app.setDelegate_(_delegate)
