from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModalDecision:
    """Describe next modal state and optional UI event."""
    modal_state: dict[str, Any] | None
    ui_event: dict[str, Any] | None


def decide_close(
    *,
    trigger: Any,
    is_open: bool,
    current_screen: str | None,
    action: Any,
    is_geo_enabled: bool,
    missing_geo_screen: str,
) -> ModalDecision | None:
    """Return close decision for modal overlay.

    Return None if no close decision applies.
    """
    if (
        is_open
        and current_screen == missing_geo_screen
        and is_geo_enabled
    ):
        return ModalDecision(modal_state=None, ui_event=None)

    if trigger == "btn_close" and is_open:
        return ModalDecision(modal_state=None, ui_event=None)

    if trigger == "key_action" and action == "escape" and is_open:
        return ModalDecision(modal_state=None, ui_event=None)

    return None

def decide_screen_change(
    *,
    trigger: Any,
    is_open: bool,
    current_screen: str | None,
    show_system: bool,
    action: Any,
    menu_screens: set[str],
    menu_commands: set[str],
    open_ports_prefs: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return new modal_state for screen transitions.

    Return None if no screen change applies.
    """
    # Keyboard open modal
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

    # Toggle inside Open Ports modal
    if trigger == "toggle_open_ports_system":
        if not is_open or current_screen != "menu_open_ports":
            return None

        return {
            "screen": "menu_open_ports",
            "payload": {"show_system": show_system},
        }

    # Open modal from menu_* click
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
    """Return modal decision for map click.

    Open the map_click screen when the map is clicked
    and click_data is present. Return None otherwise.
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
        ui_event=None,
    )

def decide_geo_recheck(
    *,
    trigger: Any,
    check_db_clicks: int | None,
    evt_type: str,
    now_iso: str,
) -> ModalDecision | None:
    """Return modal decision for GeoIP recheck request.

    Emit EVT_GEO_RECHECK event when the check databases
    button is triggered. Return None otherwise.
    """
    if trigger != "btn_check_databases":
        return None

    if not isinstance(check_db_clicks, int) or check_db_clicks < 1:
        return None

    return ModalDecision(
        modal_state=None,
        ui_event={"type": evt_type, "t": now_iso},
    )