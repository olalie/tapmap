"""System tray icon: the minimal Open TapMap / Quit TapMap menu.

Expected tray-availability failures degrade to "no tray" so TapMap can
continue running without one.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pystray import Icon

logger = logging.getLogger(__name__)


def create_tray_icon(
    *,
    icon_path: Path,
    tooltip: str,
    on_open: Callable[[], None],
    on_quit: Callable[[], None],
) -> Icon | None:
    """Build the tray icon with its Open/Quit menu, or return None if unavailable."""
    try:
        import pystray
        from PIL import Image

        menu = pystray.Menu(
            pystray.MenuItem("Open TapMap", lambda icon, item: on_open(), default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit TapMap", lambda icon, item: on_quit()),
        )
        return pystray.Icon(
            "tapmap",
            icon=Image.open(icon_path),
            title=tooltip,
            menu=menu,
        )
    except (ImportError, OSError, ValueError):
        # gi.require_version() raises ValueError when the AppIndicator typelib is missing.
        logger.warning("Tray icon unavailable; continuing without one.", exc_info=True)
        return None
