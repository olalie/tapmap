"""Tests for keyboard action parsing."""

import re
from pathlib import Path

from tapmap.state import keyboard

_KEYBOARD_JS_PATH = (
    Path(__file__).resolve().parent.parent / "src" / "tapmap" / "assets" / "keyboard.js"
)

# menu_zoom_connections' "z" is dispatched by modebar.js via a UI control, not by
# keyboard.js's keydown allowlist, so it is exempt from the cross-check below.
_KEYS_SENT_OUTSIDE_KEYBOARD_JS = {"z"}


def _js_shortcut_keys() -> set[str]:
    """Return the single-character keys allowlisted in keyboard.js's shortcuts Set.

    keyboard.js gates which keystrokes are even sent to the server before
    KEY_MAP ever sees them, so a key missing from this allowlist silently
    never reaches build_key_action, regardless of KEY_MAP.
    """
    text = _KEYBOARD_JS_PATH.read_text(encoding="utf-8")
    match = re.search(r"new Set\(\[(.*?)\]\)", text, re.DOTALL)
    assert match is not None, "keyboard.js shortcuts Set literal not found"
    return set(re.findall(r'"(\w)"', match.group(1)))


class DummyDatetime:
    """Provide deterministic timestamp for tests."""

    @classmethod
    def now(cls):
        """Return fixed datetime."""
        class _T:
            def isoformat(self):
                return "2026-01-01T00:00:00"
        return _T()


def test_build_key_action_returns_none_for_empty_value() -> None:
    """Return None when capture value is empty."""
    assert keyboard.build_key_action("") is None


def test_build_key_action_returns_none_for_unknown_token() -> None:
    """Return None when token is not mapped."""
    assert keyboard.build_key_action("__q__") is None


def test_build_key_action_parses_simple_token(monkeypatch) -> None:
    """Return action payload for mapped token."""
    monkeypatch.setattr(keyboard, "datetime", DummyDatetime)

    result = keyboard.build_key_action("__h__")

    assert result == {
        "action": "menu_help",
        "t": "2026-01-01T00:00:00",
    }


def test_build_key_action_ignores_suffix_after_pipe(monkeypatch) -> None:
    """Ignore suffix after pipe separator."""
    monkeypatch.setattr(keyboard, "datetime", DummyDatetime)

    result = keyboard.build_key_action("__a__|123")

    assert result == {
        "action": "menu_about",
        "t": "2026-01-01T00:00:00",
    }


def test_build_key_action_maps_escape(monkeypatch) -> None:
    """Map escape token correctly."""
    monkeypatch.setattr(keyboard, "datetime", DummyDatetime)

    result = keyboard.build_key_action("__esc__")

    assert result == {
        "action": "escape",
        "t": "2026-01-01T00:00:00",
    }


def test_build_key_action_maps_export_cache(monkeypatch) -> None:
    """Map E token to export cache action."""
    monkeypatch.setattr(keyboard, "datetime", DummyDatetime)

    result = keyboard.build_key_action("__e__")

    assert result == {
        "action": "menu_export_cache",
        "t": "2026-01-01T00:00:00",
    }


def test_build_key_action_maps_geodb_management(monkeypatch) -> None:
    """Map G token to GeoDB management action."""
    monkeypatch.setattr(keyboard, "datetime", DummyDatetime)

    result = keyboard.build_key_action("__g__")

    assert result == {
        "action": "menu_geodb_management",
        "t": "2026-01-01T00:00:00",
    }


def test_build_key_action_maps_technical_details(monkeypatch) -> None:
    """Map T token to technical details toggle action."""
    monkeypatch.setattr(keyboard, "datetime", DummyDatetime)

    result = keyboard.build_key_action("__t__")

    assert result == {
        "action": "menu_technical_details",
        "t": "2026-01-01T00:00:00",
    }


def test_build_key_action_maps_significant_connections(monkeypatch) -> None:
    """Map S token to the Significant Connections screen action."""
    monkeypatch.setattr(keyboard, "datetime", DummyDatetime)

    result = keyboard.build_key_action("__s__")

    assert result == {
        "action": "menu_significant_connections",
        "t": "2026-01-01T00:00:00",
    }


def test_build_key_action_maps_autostart(monkeypatch) -> None:
    """Map the R key to the autostart action."""
    monkeypatch.setattr(keyboard, "datetime", DummyDatetime)

    result = keyboard.build_key_action("__r__")

    assert result == {
        "action": "menu_autostart",
        "t": "2026-01-01T00:00:00",
    }


def test_build_key_action_maps_notifications(monkeypatch) -> None:
    """Map the N key to the notifications toggle action."""
    monkeypatch.setattr(keyboard, "datetime", DummyDatetime)

    result = keyboard.build_key_action("__n__")

    assert result == {
        "action": "menu_notifications",
        "t": "2026-01-01T00:00:00",
    }


# --- keyboard.js allowlist: keys must actually reach the server ---


def test_keyboard_js_allows_the_notifications_key() -> None:
    """N must be allowlisted in keyboard.js, or key_capture never receives it."""
    assert "n" in _js_shortcut_keys()


def test_keyboard_js_allows_every_single_letter_key_map_action() -> None:
    """Every single-letter KEY_MAP token must be allowlisted in keyboard.js.

    Guards against the class of bug where a new shortcut is added to
    KEY_MAP but the keydown listener's allowlist is never updated to match,
    so the keystroke is silently dropped before it reaches Python at all.
    """
    single_letter_tokens = {
        token.strip("_") for token in keyboard.KEY_MAP if len(token.strip("_")) == 1
    }

    assert single_letter_tokens - _KEYS_SENT_OUTSIDE_KEYBOARD_JS <= _js_shortcut_keys()
