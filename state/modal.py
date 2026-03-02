"""Modal state transition logic.

Provide pure decision functions for closing,
opening, and switching modal screens.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModalDecision:
    """Describe the next modal_state value for the modal controller."""
    modal_state: dict[str, Any] | None


def decide_close(
    *,
    trigger: Any,
    is_open: bool,
    current_screen: str | None,
    action: Any,
    is_geo_enabled: bool,
    missing_geo_screen: str,
) -> ModalDecision | None:
    """Decide whether the modal should close.

    Return ModalDecision(modal_state=None) to close the modal.
    Return None if no close rule applies.
    """
    # Auto close the missing Geo DB modal once GeoIP is enabled.
    if (
        is_open
        and current_screen == missing_geo_screen
        and is_geo_enabled
    ):
        return ModalDecision(modal_state=None)

    if trigger == "btn_close" and is_open:
        return ModalDecision(modal_state=None)

    if trigger == "key_action" and action == "escape" and is_open:
        return ModalDecision(modal_state=None)

    return None

def decide_screen_change(
    *,
    trigger: Any,
    is_open: bool,
    current_screen: str | None,
    show_system: bool,
    action: Any,
    menu_screens: set[str],
    open_ports_prefs: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Decide whether the modal should switch to a different screen.

    Return a partial modal_state dict with "screen" and optional "payload".
    Return None if no screen change applies.
    """
    # Open a modal screen from keyboard action.
    if trigger == "key_action" and isinstance(action, str) and action in menu_screens:
        screen = action
        payload: dict[str, Any] = {}

        if screen == "menu_open_ports":
            prefs = open_ports_prefs or {}
            payload["show_system"] = bool(prefs.get("show_system", False))

        return {
            "screen": screen,
            "payload": payload,
        }

    # Update Open Ports payload when the toggle changes.
    if trigger == "toggle_open_ports_system":
        if not is_open or current_screen != "menu_open_ports":
            return None

        return {
            "screen": "menu_open_ports",
            "payload": {"show_system": show_system},
        }

    # Open a modal screen from menu click.
    if trigger in menu_screens:
        screen = str(trigger)
        payload: dict[str, Any] = {}

        if screen == "menu_open_ports":
            prefs = open_ports_prefs or {}
            payload["show_system"] = bool(prefs.get("show_system", False))

        return {
            "screen": screen,
            "payload": payload,
        }

    return None

def decide_map_click(
    *,
    trigger: Any,
    click_data: Any,
    now_iso: str,
) -> ModalDecision | None:
    """Open the map_click modal for valid map click data.

    Return ModalDecision for the map_click screen, or None if not applicable.
    """
    if trigger != "map":
        return None

    if click_data is None:
        return None

    return ModalDecision(
        modal_state={
            "screen": "map_click",
            "t": now_iso,
            "payload": {"click_data": click_data},
        },
    )
