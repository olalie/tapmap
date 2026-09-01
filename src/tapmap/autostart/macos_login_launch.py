"""Detect whether the installed macOS app was launched as a login item.

An AppKit delegate registers a handler for kAEOpenApplication in
applicationWillFinishLaunching_, before NSApplication's own default Apple
Event handling would otherwise consume it. When the event arrives during
NSApplication.run()'s normal startup, keyAEPropData is inspected for
keyAELaunchedAsLogInItem ('lgit'); its presence means SMAppService.mainApp
launched this process at login rather than the user launching it manually.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Final

import objc
from AppKit import NSApplication
from Foundation import NSAppleEventManager, NSObject

logger = logging.getLogger(__name__)

# FourCharCode (OSType) constants from Apple's AE headers. PyObjC does not
# export these; they are defined directly from their documented 4-character
# codes (AppleEvents.h, AERegistry.h).
_K_CORE_EVENT_CLASS: Final[int] = 0x61657674  # 'aevt'
_K_AE_OPEN_APPLICATION: Final[int] = 0x6F617070  # 'oapp'
_KEY_AE_PROP_DATA: Final[int] = 0x70726474  # 'prdt'
_KEY_AE_LAUNCHED_AS_LOGIN_ITEM: Final[int] = 0x6C676974  # 'lgit'

# NSApplication.delegate does not retain its delegate; this keeps the only
# strong reference for the life of the process.
_delegate: _LoginLaunchDelegate | None = None


class _LoginLaunchDelegate(NSObject):
    """AppKit delegate that reports the login-launch decision exactly once."""

    def initWithCallback_(self, callback: Callable[[bool], None]) -> _LoginLaunchDelegate | None:
        """Store the callback to invoke once the launch event is inspected."""
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
        """Inspect the launch event and report the login-launch decision once."""
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
    """Install the AppKit delegate that reports the login-launch decision once.

    Must be called before NSApplication.run() starts (before pystray's tray
    icon enters the AppKit event loop), so applicationWillFinishLaunching_
    can register the Apple Event handler in time to see the launch event.
    on_decision is called at most once, from the main thread, with True if
    the launch event carried keyAELaunchedAsLogInItem, False otherwise.
    """
    global _delegate
    app = NSApplication.sharedApplication()
    _delegate = _LoginLaunchDelegate.alloc().initWithCallback_(on_decision)
    app.setDelegate_(_delegate)
