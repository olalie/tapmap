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