"""Pytest configuration and session-wide stubs.

pycountry is a runtime dependency that is not available in all test
environments (e.g. when the system Python is used instead of the
project venv).  None of the tests exercise pycountry directly, so a
lightweight stub is sufficient to allow collection and import to succeed.
"""
import sys
from unittest.mock import MagicMock

if "pycountry" not in sys.modules:
    sys.modules["pycountry"] = MagicMock()
