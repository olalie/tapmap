from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .runtime import RuntimeContext


class _TapMapFormatter(logging.Formatter):
    """Formatter for TapMap log files.

    Removes trailing CR/LF from formatted log output to avoid duplicate blank
    lines and optionally inserts a blank line before records marked as a
    section break.
    """

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record).rstrip("\r\n")
        if getattr(record, "section_break", False):
            formatted = "\n" + formatted
        return formatted


def configure_logging(runtime: RuntimeContext) -> None:
    """Configure logging to the application data directory."""
    log_path = runtime.app_data_dir / "tapmap.log"
    handler = RotatingFileHandler(
        log_path,
        maxBytes=100_000,
        backupCount=3,
        encoding="utf-8",
        delay=True,
    )
    handler.setFormatter(
        _TapMapFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    logging.getLogger("werkzeug").setLevel(logging.WARNING)
