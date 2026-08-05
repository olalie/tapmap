"""Value normalization and formatting helpers for the UI.

Provide small utility functions used when rendering
values in the TapMap interface.
"""

from __future__ import annotations

import re
from typing import Any

_CAMEL_CASE_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


def safe_str(value: Any) -> str:
    """Return empty string for None, otherwise str(value)."""
    return "" if value is None else str(value)


def safe_int(value: Any, default: int = -1) -> int:
    """Convert value to int, or return default on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def scope_rank(scope: str) -> int:
    """Return sort rank for scope values."""
    order = {"PUBLIC": 0, "LAN": 1, "LOCAL": 2}
    return order.get(scope.upper(), 9)


def port_from_local(addr: str) -> int:
    """Extract port from an 'ip:port' string."""
    try:
        return int(addr.rsplit(":", 1)[-1])
    except (ValueError, TypeError):
        return -1


def strip_port(addr: str) -> str:
    """Remove trailing ':port' from an address string."""
    if not addr:
        return ""

    s = addr.strip()

    if s.startswith("["):
        end = s.find("]")
        return s[1:end].strip() if end != -1 else s

    if s.count(":") == 1:
        return s.rsplit(":", 1)[0].strip()

    return s


def pretty_bind_ip(ip: str) -> str:
    """Map wildcard bind addresses to readable labels."""
    if ip == "0.0.0.0":
        return "ALL (IPv4)"
    if ip == "::":
        return "ALL (IPv6)"
    return ip


def country_flag(code: str | None) -> str:
    """Return a flag emoji for a two-letter ISO country code, or a globe fallback."""
    if not isinstance(code, str) or len(code) != 2:
        return "🌐"
    code = code.upper()
    return chr(127397 + ord(code[0])) + chr(127397 + ord(code[1]))


_TRUST_COLORS = {
    "trusted": "#00ff66",
    "not_trusted": "#ff4444",
}


def trust_glyph(trust: str | None) -> str:
    """Return a colored bullet glyph for an app_trust value.

    Accepts "trusted", "not_trusted", "unknown", or None; any other value
    renders as unknown.
    """
    color = _TRUST_COLORS.get(trust, "#ffffff")
    return f'<span style="color:{color}">●</span>'


def humanize_camel_case(text: str) -> str:
    """Convert PascalCase/camelCase text into normal, space-separated words.

    Only the first word keeps its original casing; the rest are lowercased.
    """
    words = _CAMEL_CASE_BOUNDARY.sub(" ", text).split()
    if not words:
        return text
    return " ".join([words[0], *(w.lower() for w in words[1:])])
