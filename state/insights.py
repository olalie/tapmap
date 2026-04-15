"""Track new and seen-before IPs using epoch timestamps and bitmask."""

from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict


class InsightStateItem(TypedDict):
    """State for an IP address.

    f: first_seen (epoch seconds)
    l: last_seen (epoch seconds)
    m: 30-day activity bitmask (bit 0 = today)
    """
    f: int
    l: int   # noqa
    m: int


class InsightMetaItem(TypedDict, total=False):
    """Metadata for an IP address.

    co: country
    cc: country_code
    ci: city
    ao: asn_org
    """
    co: str | None
    cc: str | None
    ci: str | None
    ao: str | None


InsightsState = dict[str, InsightStateItem]
InsightsMeta = dict[str, InsightMetaItem]


class Insights(TypedDict):
    """Insights data structure."""
    state: InsightsState
    meta: InsightsMeta

def update_state(
    ips: set[str],
    state: InsightsState,
    now: datetime,
) -> None:
    """Update state for all observed IPs."""
    today = now.date()
    ts = int(now.timestamp())

    for ip in ips:
        if ip not in state:
            state[ip] = {
                "f": ts,
                "l": ts,
                "m": 1,
            }
            continue

        item = state[ip]

        last_date = datetime.fromtimestamp(item["l"]).date()
        delta = (today - last_date).days

        if delta >= 30:
            item["m"] = 0
        elif delta > 0:
            item["m"] <<= delta
            item["m"] &= (1 << 30) - 1

        item["m"] |= 1
        item["l"] = ts

    # prune after update
    to_delete = [ip for ip, item in state.items() if item["m"] == 0]
    for ip in to_delete:
        del state[ip]

def process_insights(
    items: list[dict[str, Any]],
    insights: dict[str, Any],
    now: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Process snapshot and return new and seen-before entries."""
    state: InsightsState = insights.setdefault("state", {})
    meta: InsightsMeta = insights.setdefault("meta", {})

    ips: set[str] = set()

    for item in items:
        if not isinstance(item, dict):
            continue

        ip = item.get("ip")
        if not isinstance(ip, str) or not ip:
            continue

        if item.get("service_scope") != "PUBLIC":
            continue

        ips.add(ip)

        if ip not in meta:
            meta[ip] = {
                "co": item.get("country"),
                "cc": item.get("country_code"),
                "ci": item.get("city"),
                "ao": item.get("asn_org"),
            }
           
    update_state(ips, state, now)
    new_countries: set[str] = set()

    for ip, item in state.items():
        mask = item["m"]

        if (mask & 1) != 1:
            continue

        if (mask >> 1) != 0:
            continue

        m = meta.get(ip)
        if not m:
            continue

        cc = m.get("cc")
        if isinstance(cc, str) and cc:
            new_countries.add(cc)

    new_countries = sorted(new_countries)
    new = {
        "countries": [],
        "providers": [],
        "ports": [],
        "applications": [],
    }

    for cc in new_countries:
        country_name = next(
            (m.get("co") for m in meta.values() if m.get("cc") == cc),
            None,
        )

        new["countries"].append(
            {
                "value": cc,
                "name": country_name,
            }
        )

    seen_before = []
    return new, seen_before
