"""Test GeoInfo lookup, enrichment, and cache behavior."""

from pathlib import Path

from tapmap.model import geoinfo
from tapmap.model.geoinfo import GeoInfo


class FakeReader:
    """Provide a minimal MaxMind reader stub."""

    def __init__(self, mapping):
        self._mapping = mapping
        self.calls = []
        self.closed = False

    def get(self, ip):
        """Return mapped value for IP."""
        self.calls.append(ip)
        return self._mapping.get(ip)

    def close(self):
        """Mark reader as closed."""
        self.closed = True

    def metadata(self):
        """Return minimal metadata with build_epoch for file validation flows."""
        class Meta:
            build_epoch = 1_714_521_600

        return Meta()


def test_lookup_returns_empty_result_for_empty_ip(tmp_path: Path) -> None:
    """Verify empty IP returns an empty lookup result."""
    geo = GeoInfo(tmp_path)

    assert geo.lookup("") == {
        "lat": None,
        "lon": None,
        "city": None,
        "country": None,
        "country_code": None,
        "asn": None,
        "asn_org": None,
    }


def test_lookup_combines_city_and_asn_data(monkeypatch, tmp_path: Path) -> None:
    """Verify lookup merges city and ASN fields into one result."""
    city_db = tmp_path / GeoInfo.CITY_DB_NAME
    asn_db = tmp_path / GeoInfo.ASN_DB_NAME
    city_db.write_text("", encoding="utf-8")
    asn_db.write_text("", encoding="utf-8")

    city_reader = FakeReader(
        {
            "203.0.113.10": {
                "location": {"latitude": 59.91, "longitude": 10.75},
                "city": {"names": {"en": "Oslo"}},
                "country": {
                    "names": {"en": "Norway"},
                    "iso_code": "NO",
                },
            }
        }
    )
    asn_reader = FakeReader(
        {
            "203.0.113.10": {
                "autonomous_system_number": 64500,
                "autonomous_system_organization": "Example Networks",
            }
        }
    )

    def fake_open_database(path):
        if path == city_db:
            return city_reader
        if path == asn_db:
            return asn_reader
        raise AssertionError(f"Unexpected database path: {path}")

    monkeypatch.setattr(geoinfo.maxminddb, "open_database", fake_open_database)

    geo = GeoInfo(tmp_path)

    assert geo.city_enabled is True
    assert geo.asn_enabled is True
    assert geo.enabled is True

    result = geo.lookup("203.0.113.10")

    assert result == {
        "lat": 59.91,
        "lon": 10.75,
        "city": "Oslo",
        "country": "Norway",
        "country_code": "NO",
        "asn": 64500,
        "asn_org": "Example Networks",
    }


def test_lookup_uses_cache_for_repeated_ip(monkeypatch, tmp_path: Path) -> None:
    """Verify repeated lookup uses cached result."""
    city_db = tmp_path / GeoInfo.CITY_DB_NAME
    city_db.write_text("", encoding="utf-8")

    city_reader = FakeReader(
        {
            "203.0.113.20": {
                "location": {"latitude": 60.0, "longitude": 11.0},
                "city": {"names": {"en": "Test City"}},
                "country": {
                    "names": {"en": "Test Country"},
                    "iso_code": "TC",
                },
            }
        }
    )

    monkeypatch.setattr(geoinfo.maxminddb, "open_database", lambda path: city_reader)

    geo = GeoInfo(tmp_path)

    first = geo.lookup("203.0.113.20")
    second = geo.lookup("203.0.113.20")

    assert first == second
    assert city_reader.calls == ["203.0.113.20"]


def test_enrich_updates_connections_in_place(monkeypatch, tmp_path: Path) -> None:
    """Verify enrich updates connection dictionaries in place."""
    city_db = tmp_path / GeoInfo.CITY_DB_NAME
    asn_db = tmp_path / GeoInfo.ASN_DB_NAME
    city_db.write_text("", encoding="utf-8")
    asn_db.write_text("", encoding="utf-8")

    city_reader = FakeReader(
        {
            "203.0.113.30": {
                "location": {"latitude": 51.5, "longitude": -0.1},
                "city": {"names": {"en": "London"}},
                "country": {
                    "names": {"en": "United Kingdom"},
                    "iso_code": "GB",
                },
            }
        }
    )
    asn_reader = FakeReader(
        {
            "203.0.113.30": {
                "autonomous_system_number": 64530,
                "autonomous_system_organization": "Example ISP",
            }
        }
    )

    def fake_open_database(path):
        if path == city_db:
            return city_reader
        if path == asn_db:
            return asn_reader
        raise AssertionError(f"Unexpected database path: {path}")

    monkeypatch.setattr(geoinfo.maxminddb, "open_database", fake_open_database)

    geo = GeoInfo(tmp_path)

    connections = [
        {"raddr_ip": "203.0.113.30", "proto": "tcp"},
        {"raddr_ip": "", "proto": "tcp"},
        {"proto": "udp"},
        "not-a-dict",
    ]

    result = geo.enrich(connections)

    assert result is connections
    assert connections[0]["lat"] == 51.5
    assert connections[0]["lon"] == -0.1
    assert connections[0]["city"] == "London"
    assert connections[0]["country"] == "United Kingdom"
    assert connections[0]["country_code"] == "GB"
    assert connections[0]["asn"] == 64530
    assert connections[0]["asn_org"] == "Example ISP"
    assert "lat" not in connections[1]
    assert "lat" not in connections[2]


def test_close_closes_open_readers(monkeypatch, tmp_path: Path) -> None:
    """Verify close closes readers and clears enabled state."""
    city_db = tmp_path / GeoInfo.CITY_DB_NAME
    asn_db = tmp_path / GeoInfo.ASN_DB_NAME
    city_db.write_text("", encoding="utf-8")
    asn_db.write_text("", encoding="utf-8")

    city_reader = FakeReader({})
    asn_reader = FakeReader({})

    def fake_open_database(path):
        if path == city_db:
            return city_reader
        if path == asn_db:
            return asn_reader
        raise AssertionError(f"Unexpected database path: {path}")

    monkeypatch.setattr(geoinfo.maxminddb, "open_database", fake_open_database)

    geo = GeoInfo(tmp_path)
    geo.close()

    assert city_reader.closed is True
    assert asn_reader.closed is True
    assert geo.city_enabled is False
    assert geo.asn_enabled is False
    assert geo.enabled is False


def test_reload_reopens_readers(monkeypatch, tmp_path: Path) -> None:
    """Verify reload closes and reopens database readers."""
    city_db = tmp_path / GeoInfo.CITY_DB_NAME
    city_db.write_text("", encoding="utf-8")

    readers = [FakeReader({}), FakeReader({})]

    def fake_open_database(path):
        assert path == city_db
        return readers.pop(0)

    monkeypatch.setattr(geoinfo.maxminddb, "open_database", fake_open_database)

    geo = GeoInfo(tmp_path)
    first_reader = geo._city_reader

    assert first_reader is not None
    assert geo.reload() is True
    assert first_reader.closed is True
    assert geo._city_reader is not first_reader


def test_open_readers_falls_back_to_dbip_file_names(monkeypatch, tmp_path: Path) -> None:
    """Verify GeoInfo opens DB-IP file names when GeoLite2 files are absent."""
    city_db = tmp_path / GeoInfo.DBIP_CITY_DB_NAME
    asn_db = tmp_path / GeoInfo.DBIP_ASN_DB_NAME
    city_db.write_text("", encoding="utf-8")
    asn_db.write_text("", encoding="utf-8")

    city_reader = FakeReader({})
    asn_reader = FakeReader({})

    def fake_open_database(path):
        if path == city_db:
            return city_reader
        if path == asn_db:
            return asn_reader
        raise AssertionError(f"Unexpected database path: {path}")

    monkeypatch.setattr(geoinfo.maxminddb, "open_database", fake_open_database)

    geo = GeoInfo(tmp_path)

    assert geo.city_enabled is True
    assert geo.asn_enabled is True
    assert geo.enabled is True


def test_cache_eviction_discards_oldest_entry(monkeypatch, tmp_path: Path) -> None:
    """Verify cache evicts the least recently used entry."""
    city_db = tmp_path / GeoInfo.CITY_DB_NAME
    city_db.write_text("", encoding="utf-8")

    city_reader = FakeReader(
        {
            "203.0.113.1": {"location": {"latitude": 1.0, "longitude": 1.0}},
            "203.0.113.2": {"location": {"latitude": 2.0, "longitude": 2.0}},
            "203.0.113.3": {"location": {"latitude": 3.0, "longitude": 3.0}},
        }
    )

    monkeypatch.setattr(geoinfo.maxminddb, "open_database", lambda path: city_reader)

    geo = GeoInfo(tmp_path, cache_size=2)

    geo.lookup("203.0.113.1")
    geo.lookup("203.0.113.2")
    geo.lookup("203.0.113.3")

    assert list(geo._ip_cache.keys()) == ["203.0.113.2", "203.0.113.3"]


def test_context_manager_closes_readers(monkeypatch, tmp_path: Path) -> None:
    """Verify context manager closes readers on exit."""
    city_db = tmp_path / GeoInfo.CITY_DB_NAME
    city_db.write_text("", encoding="utf-8")

    city_reader = FakeReader({})

    monkeypatch.setattr(geoinfo.maxminddb, "open_database", lambda path: city_reader)

    with GeoInfo(tmp_path) as geo:
        assert geo.city_enabled is True

    assert city_reader.closed is True
