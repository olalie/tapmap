"""Test classification helpers in model.Model."""

from tapmap.model.model import Model


def test_service_scope_classifies_addresses() -> None:
    """Verify service scope classification for common address types."""
    assert Model._service_scope("127.0.0.1") == "LOCAL"
    assert Model._service_scope("::1") == "LOCAL"
    assert Model._service_scope("192.168.1.10") == "LAN"
    assert Model._service_scope("fe80::1") == "LAN"
    assert Model._service_scope("8.8.8.8") == "PUBLIC"
    assert Model._service_scope(None) == "UNKNOWN"
    assert Model._service_scope("bad-ip") == "UNKNOWN"


def test_bind_scope_classifies_addresses() -> None:
    """Verify bind scope classification for common bind addresses."""
    assert Model._bind_scope("127.0.0.1") == "LOCAL"
    assert Model._bind_scope("::1") == "LOCAL"
    assert Model._bind_scope("192.168.1.10") == "LAN"
    assert Model._bind_scope("fe80::1") == "LAN"
    assert Model._bind_scope("8.8.8.8") == "PUBLIC"
    assert Model._bind_scope("0.0.0.0") == "PUBLIC"
    assert Model._bind_scope("::") == "PUBLIC"
    assert Model._bind_scope(None) == "UNKNOWN"
    assert Model._bind_scope("bad-ip") == "UNKNOWN"


def test_is_map_candidate_requires_public_scope_and_coordinates() -> None:
    """Verify map candidate classification requires PUBLIC scope and coordinates."""
    assert (
        Model._is_map_candidate(
            {
                "service_scope": "PUBLIC",
                "lat": 59.91,
                "lon": 10.75,
            }
        )
        is True
    )

    assert (
        Model._is_map_candidate(
            {
                "service_scope": "LAN",
                "lat": 59.91,
                "lon": 10.75,
            }
        )
        is False
    )

    assert (
        Model._is_map_candidate(
            {
                "service_scope": "PUBLIC",
                "lat": None,
                "lon": 10.75,
            }
        )
        is False
    )

    assert (
        Model._is_map_candidate(
            {
                "service_scope": "PUBLIC",
                "lat": 59.91,
                "lon": None,
            }
        )
        is False
    )

    assert (
        Model._is_map_candidate(
            {
                "service_scope": "UNKNOWN",
                "lat": 59.91,
                "lon": 10.75,
            }
        )
        is False
    )
