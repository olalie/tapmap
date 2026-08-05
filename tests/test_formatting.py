"""Tests for UI formatting helpers."""

from __future__ import annotations

from tapmap.ui.formatting import humanize_camel_case


def test_humanize_camel_case_splits_multiple_words() -> None:
    """PascalCase text becomes space-separated, lowercased after the first word."""
    assert humanize_camel_case("TrustedAndSigned") == "Trusted and signed"


def test_humanize_camel_case_splits_two_words() -> None:
    """A two-word PascalCase value splits into two words."""
    assert humanize_camel_case("SignatureInvalid") == "Signature invalid"


def test_humanize_camel_case_single_word_is_unchanged() -> None:
    """A single word with no case boundary is returned as-is."""
    assert humanize_camel_case("Trusted") == "Trusted"


def test_humanize_camel_case_empty_string_returns_empty_string() -> None:
    """An empty string is returned unchanged."""
    assert humanize_camel_case("") == ""
