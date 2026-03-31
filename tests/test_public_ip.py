"""Test public IP lookup helpers."""

from urllib.error import URLError

import model.public_ip as public_ip


class FakeResponse:
    """Provide a minimal urlopen response stub."""

    def __init__(self, body: str) -> None:
        self._body = body

    def read(self) -> bytes:
        """Return response body as bytes."""
        return self._body.encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        """Return context manager entry value."""
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        """Propagate exceptions from the context block."""
        return False


def test_iter_public_ip_candidates_yields_valid_addresses(monkeypatch) -> None:
    """Verify valid IPv4 and IPv6 responses are yielded."""
    responses = iter(
        [
            FakeResponse("203.0.113.10\n"),
            FakeResponse("2001:db8::10\n"),
        ]
    )

    monkeypatch.setattr(public_ip.ssl, "create_default_context", lambda cafile: object())
    monkeypatch.setattr(public_ip.certifi, "where", lambda: "/fake/cacert.pem")
    monkeypatch.setattr(public_ip, "IP_SERVICES", ("https://svc1", "https://svc2"))
    monkeypatch.setattr(
        public_ip,
        "urlopen",
        lambda request, timeout, context: next(responses),
    )

    result = list(public_ip.iter_public_ip_candidates())

    assert result == ["203.0.113.10", "2001:db8::10"]


def test_iter_public_ip_candidates_skips_errors_and_invalid_values(monkeypatch) -> None:
    """Verify lookup skips failing and invalid responses."""
    responses = iter(
        [
            URLError("boom"),
            FakeResponse("not-an-ip\n"),
            FakeResponse("203.0.113.20\n"),
        ]
    )

    def fake_urlopen(request, timeout, context):
        value = next(responses)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(public_ip.ssl, "create_default_context", lambda cafile: object())
    monkeypatch.setattr(public_ip.certifi, "where", lambda: "/fake/cacert.pem")
    monkeypatch.setattr(
        public_ip,
        "IP_SERVICES",
        ("https://svc1", "https://svc2", "https://svc3"),
    )
    monkeypatch.setattr(public_ip, "urlopen", fake_urlopen)

    result = list(public_ip.iter_public_ip_candidates())

    assert result == ["203.0.113.20"]


def test_get_public_ip_returns_first_valid_candidate(monkeypatch) -> None:
    """Verify get_public_ip returns the first valid address."""
    monkeypatch.setattr(
        public_ip,
        "iter_public_ip_candidates",
        lambda timeout_s=public_ip.DEFAULT_TIMEOUT_S: iter(
            ["203.0.113.30", "2001:db8::30"]
        ),
    )

    result = public_ip.get_public_ip()

    assert result == "203.0.113.30"


def test_get_public_ip_returns_none_when_no_candidates(monkeypatch) -> None:
    """Verify get_public_ip returns None when no address is found."""
    monkeypatch.setattr(
        public_ip,
        "iter_public_ip_candidates",
        lambda timeout_s=public_ip.DEFAULT_TIMEOUT_S: iter(()),
    )

    result = public_ip.get_public_ip()

    assert result is None
