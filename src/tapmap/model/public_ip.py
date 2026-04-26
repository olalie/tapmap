"""Provide public IP lookup utilities.

Query external services for the host public IP address and validate the result
as an IPv4 or IPv6 address.
"""

from __future__ import annotations

import ipaddress
import logging
import ssl
from collections.abc import Iterator
from typing import Final
from urllib.error import URLError
from urllib.request import Request, urlopen

import certifi

LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S: Final[float] = 2.0
USER_AGENT: Final[str] = "TapMap/1.0 (+https://github.com/olalie/tapmap)"

IP_SERVICES: Final[tuple[str, ...]] = (
    "https://api.ipify.org",  # often IPv4
    "https://checkip.amazonaws.com",  # often IPv4
    "https://ifconfig.me/ip",  # often IPv6
    "https://icanhazip.com",  # often IPv6
)


def iter_public_ip_candidates(*, timeout_s: float = DEFAULT_TIMEOUT_S) -> Iterator[str]:
    """Yield validated public IP addresses from multiple services.

    Args:
        timeout_s: Request timeout in seconds.

    Yields:
        Public IP addresses as IPv4 or IPv6 strings.
    """
    context = ssl.create_default_context(cafile=certifi.where())

    for url in IP_SERVICES:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(request, timeout=timeout_s, context=context) as resp:
                raw_ip = resp.read().decode("utf-8").strip()
        except URLError as exc:
            LOGGER.debug("Public IP lookup failed for %s: %s", url, exc)
            continue

        try:
            ipaddress.ip_address(raw_ip)
        except ValueError:
            LOGGER.debug("Public IP lookup returned invalid IP from %s: %r", url, raw_ip)
            continue

        yield raw_ip


def get_public_ip(*, timeout_s: float = DEFAULT_TIMEOUT_S) -> str | None:
    """Return the first validated public IP address, or None."""
    return next(iter_public_ip_candidates(timeout_s=timeout_s), None)
