from __future__ import annotations

from typing import Any


def compute_menu_open_state(
    *,
    trigger: Any,
    menu_open: Any,
    key_action: Any,
    menu_screens: set[str],
    menu_commands: set[str],
) -> bool | None:
    """Compute next menu open state, or return None for no update."""
    if trigger == "btn_menu":
        return not bool(menu_open)

    if trigger == "menu_overlay":
        return False

    if (
        trigger == "key_action"
        and isinstance(key_action, dict)
        and key_action.get("action") == "escape"
        and bool(menu_open)
    ):
        return False

    if trigger in (menu_screens | menu_commands):
        return False

    return None