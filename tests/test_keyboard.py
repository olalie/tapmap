"""Tests for keyboard action parsing."""

from tapmap.state import keyboard


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


def test_build_key_action_maps_autostart(monkeypatch) -> None:
    """Map the R key to the autostart action."""
    monkeypatch.setattr(keyboard, "datetime", DummyDatetime)

    result = keyboard.build_key_action("__r__")

    assert result == {
        "action": "menu_autostart",
        "t": "2026-01-01T00:00:00",
    }
