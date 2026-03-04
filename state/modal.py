"""Modal state transition logic.

Provide pure decision functions for closing, opening, and switching modal screens.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class ModalRoute:
    """Describe the next high level modal controller route.

    action:
      - "apply": apply modal_state (open, switch, or close)
      - "open_data": request opening the GeoIP data folder
      - "noop": no change

    modal_state:
      - full next modal_state dict, or None to close, used when action == "apply"
    """

    action: Literal["apply", "open_data", "noop"]
    modal_state: dict[str, Any] | None = None


def _decide_close(
    *,
    trigger: Any,
    is_open: bool,
    current_screen: str | None,
    action: Any,
    is_geo_enabled: bool,
    missing_geo_screen: str,
) -> dict[str, Any] | None:
    """Return None to close the modal, or no decision if not applicable."""
    # Auto close the missing Geo DB modal once GeoIP is enabled.
    if is_open and current_screen == missing_geo_screen and is_geo_enabled:
        return None

    if trigger == "btn_close" and is_open:
        return None

    if trigger == "key_action" and action == "escape" and is_open:
        return None

    return ...  # sentinel meaning "no decision"


def _decide_screen_change(
    *,
    trigger: Any,
    is_open: bool,
    current_screen: str | None,
    show_system: bool,
    action: Any,
    menu_screens: set[str],
    open_ports_prefs: dict[str, Any] | None,
    now_iso: str,
) -> dict[str, Any] | None:
    """Return full modal_state for screen transitions, or None if not applicable."""
    # Open a modal screen from keyboard action.
    if trigger == "key_action" and isinstance(action, str) and action in menu_screens:
        screen = action
        payload: dict[str, Any] = {}

        if screen == "menu_open_ports":
            prefs = open_ports_prefs or {}
            payload["show_system"] = bool(prefs.get("show_system", False))

        return {"screen": screen, "t": now_iso, "payload": payload}

    # Update Open Ports payload when the toggle changes.
    if trigger == "toggle_open_ports_system":
        if not is_open or current_screen != "menu_open_ports":
            return None
        return {"screen": "menu_open_ports", "t": now_iso, "payload": {"show_system": show_system}}

    # Open a modal screen from menu click.
    if trigger in menu_screens:
        screen = str(trigger)
        payload: dict[str, Any] = {}

        if screen == "menu_open_ports":
            prefs = open_ports_prefs or {}
            payload["show_system"] = bool(prefs.get("show_system", False))

        return {"screen": screen, "t": now_iso, "payload": payload}

    return None


def _decide_map_click(
    *,
    trigger: Any,
    click_data: Any,
    now_iso: str,
) -> dict[str, Any] | None:
    """Return full modal_state for map click, or None if not applicable."""
    if trigger != "map":
        return None
    if click_data is None:
        return None

    return {"screen": "map_click", "t": now_iso, "payload": {"click_data": click_data}}


def decide_modal_route(
    *,
    trigger: Any,
    is_open: bool,
    current_screen: str | None,
    action: Any,
    show_system: bool,
    menu_screens: set[str],
    open_ports_prefs: dict[str, Any] | None,
    click_data: Any,
    is_geo_enabled: bool,
    missing_geo_screen: str,
    now_iso: str,
) -> ModalRoute:
    """Decide modal routing in a single priority ordered function."""
    # 1) Close has highest priority (ESC, Close button, auto close).
    close_result = _decide_close(
        trigger=trigger,
        is_open=is_open,
        current_screen=current_screen,
        action=action,
        is_geo_enabled=is_geo_enabled,
        missing_geo_screen=missing_geo_screen,
    )
    if close_result is None:
        return ModalRoute(action="apply", modal_state=None)
    if close_result is not ...:
        # This should never happen, but keeps the contract explicit.
        return ModalRoute(action="noop")

    # 2) Screen routing (menu, keyboard, toggle).
    next_state = _decide_screen_change(
        trigger=trigger,
        is_open=is_open,
        current_screen=current_screen,
        show_system=show_system,
        action=action,
        menu_screens=menu_screens,
        open_ports_prefs=open_ports_prefs,
        now_iso=now_iso,
    )
    if next_state is not None:
        return ModalRoute(action="apply", modal_state=next_state)

    # 3) Side-effect request.
    if trigger == "btn_open_data":
        return ModalRoute(action="open_data")

    # 4) Map click.
    next_state = _decide_map_click(
        trigger=trigger,
        click_data=click_data,
        now_iso=now_iso,
    )
    if next_state is not None:
        return ModalRoute(action="apply", modal_state=next_state)

    return ModalRoute(action="noop")
