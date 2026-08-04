"""Tests for TapMap logging configuration."""

import logging
from pathlib import Path

import pytest

from tapmap.logging_config import _TapMapFormatter, configure_logging
from tapmap.runtime import AppMeta, RuntimeContext

_META = AppMeta(name="TapMap", version="test", author="test")


def _runtime_ctx(tmp_path: Path) -> RuntimeContext:
    """Return a minimal RuntimeContext for logging tests."""
    return RuntimeContext(
        meta=_META,
        app_data_dir=tmp_path,
        run_dir=tmp_path,
        is_frozen=False,
        net_backend="psutil",
        net_backend_version="test",
        server_host="127.0.0.1",
        server_port=8050,
        launch_browser=False,
        cache_retention_min=0,
        is_docker=False,
        location_override=None,
        security_extensions_dir=tmp_path,
    )


def _make_record(**kwargs) -> logging.LogRecord:
    """Create a log record with defaults overridden by keyword arguments."""
    defaults = {
        "name": "tapmap.test",
        "levelno": logging.INFO,
        "levelname": "INFO",
        "msg": "test message",
        "args": (),
    }
    defaults.update(kwargs)
    return logging.makeLogRecord(defaults)


@pytest.fixture
def formatter() -> _TapMapFormatter:
    """Return a formatter with a deterministic, timestamp-free format string."""
    return _TapMapFormatter("%(levelname)s %(name)s: %(message)s")


# _TapMapFormatter — trailing newline stripping


def test_formatter_strips_trailing_newline(formatter: _TapMapFormatter) -> None:
    """Trailing newline is removed from formatted output."""
    record = _make_record(msg="message\n")
    formatted = formatter.format(record)
    assert not formatted.endswith("\n")
    assert formatted == "INFO tapmap.test: message"


def test_formatter_strips_trailing_carriage_return_and_newline(formatter: _TapMapFormatter) -> None:
    """Trailing CRLF is removed from formatted output."""
    record = _make_record(msg="message\r\n")
    formatted = formatter.format(record)
    assert not formatted.endswith("\n")
    assert not formatted.endswith("\r")
    assert formatted == "INFO tapmap.test: message"


def test_formatter_preserves_internal_newlines(formatter: _TapMapFormatter) -> None:
    """Newlines within a multiline message are not stripped."""
    record = _make_record(msg="line1\nline2\nline3")
    formatted = formatter.format(record)
    assert formatted.count("\n") == 2


# _TapMapFormatter — section_break blank line


def test_formatter_section_break_prepends_blank_line(formatter: _TapMapFormatter) -> None:
    """Records marked section_break=True are preceded by a blank line."""
    record = _make_record(section_break=True)

    assert formatter.format(record).startswith("\n")


def test_formatter_without_section_break_does_not_prepend_blank_line(
    formatter: _TapMapFormatter,
) -> None:
    """Records without section_break are not prefixed with a blank line."""
    record = _make_record()

    assert not formatter.format(record).startswith("\n")


# configure_logging — integration


def test_configure_logging_creates_log_file_in_app_data_dir(tmp_path: Path) -> None:
    """configure_logging writes the log file into app_data_dir after the first record."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    try:
        configure_logging(_runtime_ctx(tmp_path))
        logging.getLogger("tapmap.test").info("probe")
        assert (tmp_path / "tapmap.log").exists()
        assert "probe" in (tmp_path / "tapmap.log").read_text()
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers.clear()
        root.handlers.extend(saved_handlers)
        root.setLevel(saved_level)
