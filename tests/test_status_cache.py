"""Tests for status cache accumulation and serialization."""

from __future__ import annotations

import state.status_cache as status_cache


def test_clear_removes_all_cached_keys() -> None:
    """Clear all cached key sets."""
    cache = status_cache.StatusCache()
    cache.sock.add(("tcp", "1.2.3.4", 80, "pid:1"))
    cache.serv.add(("tcp", "1.2.3.4", 80))
    cache.map.add(("tcp", "1.2.3.4", 80))
    cache.unm.add(("tcp", "2.3.4.5", 443))
    cache.loc.add(("tcp", "127.0.0.1", 8080))

    cache.clear()

    assert cache.sock == set()
    assert cache.serv == set()
    assert cache.map == set()
    assert cache.unm == set()
    assert cache.loc == set()


def test_update_adds_public_mapped_service_and_socket() -> None:
    """Add mapped public service and socket keys."""
    cache = status_cache.StatusCache()

    cache.update(
        [
            {
                "ip": "8.8.8.8",
                "port": 53,
                "proto": "udp",
                "pid": 100,
                "service_scope": "PUBLIC",
                "lat": 59.9,
                "lon": 10.7,
            }
        ]
    )

    assert cache.serv == {("udp", "8.8.8.8", 53)}
    assert cache.sock == {("udp", "8.8.8.8", 53, "pid:100")}
    assert cache.map == {("udp", "8.8.8.8", 53)}
    assert cache.unm == set()
    assert cache.loc == set()


def test_update_adds_public_unmapped_service_when_geo_is_missing() -> None:
    """Add unmapped public service when coordinates are missing."""
    cache = status_cache.StatusCache()

    cache.update(
        [
            {
                "ip": "1.2.3.4",
                "port": 80,
                "proto": "tcp",
                "process_name": "nginx",
                "service_scope": "PUBLIC",
            }
        ]
    )

    assert cache.serv == {("tcp", "1.2.3.4", 80)}
    assert cache.sock == {("tcp", "1.2.3.4", 80, "proc:nginx")}
    assert cache.map == set()
    assert cache.unm == {("tcp", "1.2.3.4", 80)}
    assert cache.loc == set()


def test_update_adds_local_service_to_loc_only() -> None:
    """Add LAN and LOCAL services to loc only."""
    cache = status_cache.StatusCache()

    cache.update(
        [
            {
                "ip": "192.168.1.10",
                "port": 445,
                "proto": "tcp",
                "service_scope": "LAN",
            },
            {
                "ip": "127.0.0.1",
                "port": 8000,
                "proto": "tcp",
                "service_scope": "LOCAL",
            },
        ]
    )

    assert cache.serv == {
        ("tcp", "192.168.1.10", 445),
        ("tcp", "127.0.0.1", 8000),
    }
    assert cache.loc == {
        ("tcp", "192.168.1.10", 445),
        ("tcp", "127.0.0.1", 8000),
    }
    assert cache.map == set()
    assert cache.unm == set()


def test_update_ignores_unknown_scope_for_map_classification() -> None:
    """Ignore UNKNOWN scope for map, unm, and loc counters."""
    cache = status_cache.StatusCache()

    cache.update(
        [
            {
                "ip": "5.6.7.8",
                "port": 443,
                "proto": "tcp",
                "service_scope": "UNKNOWN",
            }
        ]
    )

    assert cache.serv == {("tcp", "5.6.7.8", 443)}
    assert cache.sock == {("tcp", "5.6.7.8", 443, "proc:Unknown")}
    assert cache.map == set()
    assert cache.unm == set()
    assert cache.loc == set()


def test_update_deduplicates_service_keys_but_keeps_distinct_socket_owners() -> None:
    """Deduplicate services while keeping distinct socket owners."""
    cache = status_cache.StatusCache()

    cache.update(
        [
            {
                "ip": "9.9.9.9",
                "port": 443,
                "proto": "tcp",
                "pid": 10,
                "service_scope": "PUBLIC",
            },
            {
                "ip": "9.9.9.9",
                "port": 443,
                "proto": "tcp",
                "pid": 20,
                "service_scope": "PUBLIC",
            },
        ]
    )

    assert cache.serv == {("tcp", "9.9.9.9", 443)}
    assert cache.sock == {
        ("tcp", "9.9.9.9", 443, "pid:10"),
        ("tcp", "9.9.9.9", 443, "pid:20"),
    }
    assert cache.unm == {("tcp", "9.9.9.9", 443)}


def test_update_ignores_items_with_invalid_ip_or_port() -> None:
    """Ignore entries with invalid ip or port."""
    cache = status_cache.StatusCache()

    cache.update(
        [
            {"ip": "", "port": 80},
            {"ip": "1.2.3.4", "port": 0},
            {"ip": "1.2.3.4", "port": -1},
            {"ip": "1.2.3.4", "port": "bad"},
            {"port": 80},
        ]
    )

    assert cache.sock == set()
    assert cache.serv == set()
    assert cache.map == set()
    assert cache.unm == set()
    assert cache.loc == set()


def test_format_chain_returns_counter_summary() -> None:
    """Format counter summary for the status line."""
    cache = status_cache.StatusCache(
        sock={("tcp", "1.1.1.1", 80, "pid:1"), ("tcp", "1.1.1.1", 80, "pid:2")},
        serv={("tcp", "1.1.1.1", 80)},
        map={("tcp", "1.1.1.1", 80)},
        unm={("tcp", "2.2.2.2", 443)},
        loc={("tcp", "127.0.0.1", 8000)},
    )

    result = cache.format_chain()

    assert result == "SOCK 2 SERV 1 MAP 1 UNM 1 LOC 1"


def test_to_store_and_from_store_roundtrip_preserves_cache_content() -> None:
    """Roundtrip cache content through Dash store format."""
    original = status_cache.StatusCache(
        sock={
            ("tcp", "1.1.1.1", 80, "pid:1"),
            ("udp", "8.8.8.8", 53, "proc:dns"),
        },
        serv={
            ("tcp", "1.1.1.1", 80),
            ("udp", "8.8.8.8", 53),
        },
        map={("udp", "8.8.8.8", 53)},
        unm={("tcp", "1.1.1.1", 80)},
        loc={("tcp", "127.0.0.1", 8080)},
    )

    restored = status_cache.StatusCache.from_store(original.to_store())

    assert restored == original


def test_from_store_returns_empty_cache_for_invalid_input() -> None:
    """Return empty cache for invalid store input."""
    restored = status_cache.StatusCache.from_store(None)

    assert restored == status_cache.StatusCache()


def test_from_store_ignores_invalid_service_entries() -> None:
    """Ignore invalid service entries in store data."""
    restored = status_cache.StatusCache.from_store(
        {
            "serv": [
                ["tcp", "1.2.3.4", 80],
                ["udp", "", 53],
                ["tcp", "2.3.4.5", 0],
                ["bad", "3.4.5.6", 443],
                ["tcp", "4.5.6.7", "bad"],
                ["too", "short"],
            ]
        }
    )

    assert restored.serv == {
        ("tcp", "1.2.3.4", 80),
        ("tcp", "3.4.5.6", 443),
    }


def test_from_store_ignores_invalid_socket_entries() -> None:
    """Ignore invalid socket entries in store data."""
    restored = status_cache.StatusCache.from_store(
        {
            "sock": [
                ["tcp", "1.2.3.4", 80, "pid:1"],
                ["udp", "", 53, "pid:2"],
                ["tcp", "2.3.4.5", 0, "pid:3"],
                ["bad", "3.4.5.6", 443, ""],
                ["tcp", "4.5.6.7", "bad", "proc:x"],
                ["too", "short"],
            ]
        }
    )

    assert restored.sock == {
        ("tcp", "1.2.3.4", 80, "pid:1"),
        ("tcp", "3.4.5.6", 443, "proc:Unknown"),
    }


def test_owner_label_prefers_non_negative_pid() -> None:
    """Prefer pid label when pid is valid."""
    assert status_cache.StatusCache._owner_label(12, "python") == "pid:12"


def test_owner_label_falls_back_to_process_name() -> None:
    """Use process name when pid is invalid."""
    assert status_cache.StatusCache._owner_label(None, "python") == "proc:python"


def test_owner_label_falls_back_to_unknown_when_owner_data_is_missing() -> None:
    """Use Unknown owner label when pid and process name are missing."""
    assert status_cache.StatusCache._owner_label(None, None) == "proc:Unknown"
