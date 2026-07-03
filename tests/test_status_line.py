"""Test status line rendering."""

import pytest

from tapmap.state import status_line


class DummyStatusCache:
    """Provide a minimal status cache stub."""

    def __init__(self, chain: str) -> None:
        """Store the formatted cache chain."""
        self._chain = chain

    def format_chain(self) -> str:
        """Return the formatted cache chain."""
        return self._chain


@pytest.fixture
def cache_chain_stub(monkeypatch) -> str:
    """Stub StatusCache.from_store with a deterministic cache chain."""
    chain = "SOCK 0 SERV 0 MAP 0 UNM 0 LOC 0"

    monkeypatch.setattr(
        status_line.StatusCache,
        "from_store",
        lambda data: DummyStatusCache(chain),
    )

    return chain


def test_render_status_text_returns_flash_message_when_present(cache_chain_stub: str) -> None:
    """Return the flash message when present."""
    result = status_line.render_status_text(
        snapshot=None,
        status_cache_data=None,
        status_flash={"message": "Clearing cache..."},
        myloc_label="Oslo",
        to_int=int,
    )

    assert result == "Clearing cache..."


def test_render_status_text_returns_wait_status_when_snapshot_is_missing(
    cache_chain_stub: str,
) -> None:
    """Return WAIT status when snapshot is missing."""
    result = status_line.render_status_text(
        snapshot=None,
        status_cache_data=None,
        status_flash=None,
        myloc_label="Oslo",
        to_int=int,
    )

    assert result == (
        "STATUS: WAIT | "
        "LIVE: TCP 0 EST 0 LST 0 UDP R 0 B 0 | "
        f"CACHE: {cache_chain_stub} | "
        "UPDATED: --:--:-- | "
        "MYLOC: Oslo"
    )


def test_render_status_text_returns_error_status_with_note(cache_chain_stub: str) -> None:
    """Return ERROR status with terminal note when snapshot has error."""
    result = status_line.render_status_text(
        snapshot={"error": "boom"},
        status_cache_data=None,
        status_flash=None,
        myloc_label="Oslo",
        to_int=int,
    )

    assert result == (
        "STATUS: ERROR (see terminal) | "
        "LIVE: TCP 0 EST 0 LST 0 UDP R 0 B 0 | "
        f"CACHE: {cache_chain_stub} | "
        "UPDATED: --:--:-- | "
        "MYLOC: Oslo"
    )


def test_render_status_text_returns_ok_status_when_snapshot_has_no_error(
    cache_chain_stub: str,
) -> None:
    """Return OK status when snapshot has no error."""
    snapshot = {
        "stats": {
            "live_tcp_total": "10",
            "live_tcp_established": "4",
            "live_tcp_listen": "2",
            "live_udp_remote": "3",
            "live_udp_bound": "1",
            "updated": "10:15:30",
        }
    }

    result = status_line.render_status_text(
        snapshot=snapshot,
        status_cache_data=None,
        status_flash=None,
        myloc_label="Oslo",
        to_int=int,
    )

    assert result == (
        "STATUS: OK | "
        "LIVE: TCP 10 EST 4 LST 2 UDP R 3 B 1 | "
        f"CACHE: {cache_chain_stub} | "
        "UPDATED: 10:15:30 | "
        "MYLOC: Oslo"
    )

def test_render_status_text_uses_default_updated_when_stats_updated_is_missing(
    cache_chain_stub: str,
) -> None:
    """Keep the default updated value when stats.updated is missing."""
    snapshot = {
        "stats": {
            "live_tcp_total": "1",
            "live_tcp_established": "1",
            "live_tcp_listen": "0",
            "live_udp_remote": "0",
            "live_udp_bound": "0",
        }
    }

    result = status_line.render_status_text(
        snapshot=snapshot,
        status_cache_data=None,
        status_flash=None,
        myloc_label="Oslo",
        to_int=int,
    )

    assert result == (
        "STATUS: OK | "
        "LIVE: TCP 1 EST 1 LST 0 UDP R 0 B 0 | "
        f"CACHE: {cache_chain_stub} | "
        "UPDATED: --:--:-- | "
        "MYLOC: Oslo"
    )
