"""Smoke tests for TapMap application bootstrap."""

import tapmap
from tapmap.app import APP_META, TapMap
from tapmap.runtime import build_runtime


def test_tapmap_module_imports() -> None:
    """Import the application module."""
    assert tapmap is not None


def test_tapmap_app_constructs() -> None:
    """Construct TapMap without starting the server."""
    runtime_ctx = build_runtime(APP_META)
    app = TapMap(runtime_ctx)

    assert app.app is not None
