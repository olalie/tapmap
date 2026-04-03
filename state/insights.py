"""Track new and returning IPs with minimal state."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, TypedDict

import state


class InsightStateItem(TypedDict):
    """State for an IP address."""
    first_seen: datetime
    last_seen: datetime
    seen_times: set[datetime]


class InsightMetaItem(TypedDict, total=False):
    """Metadata for an IP address."""
    country: str | None
    country_code: str | None
    city: str | None
    asn_org: str | None


InsightsState = dict[str, InsightStateItem]
InsightsMeta = dict[str, InsightMetaItem]


class Insights(TypedDict):
    """Insights data structure."""
    state: InsightsState
    meta: InsightsMeta


def process_insights(
    
    items: list[dict[str, Any]],
    insights: dict[str, Any],
    now: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Process snapshot items and return new and returning IP entries."""
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
                "country": item.get("country"),
                "country_code": item.get("country_code"),
                "city": item.get("city"),
                "asn_org": item.get("asn_org"),
            }

    new_ips: list[str] = []
    returning_ips: list[str] = []

    for ip in ips:
        if ip not in state:
            new_ips.append(ip)
        else:
            times = state[ip]["seen_times"]
            if len(times) >= 2:
                returning_ips.append(ip)

    for ip in ips:
        if ip not in state:
            state[ip] = {
                "first_seen": now,
                "last_seen": now,
                "seen_times": {now},
            }
        else:
            item = state[ip]
            item["last_seen"] = now
            item.setdefault("seen_times", set()).add(now)

    cutoff = now - timedelta(seconds=30 * 5)

    to_delete = []

    for ip, item in state.items():
        times = item["seen_times"]
        new_times = {t for t in times if t >= cutoff}
        item["seen_times"] = new_times

        if not new_times:
            to_delete.append(ip)

    for ip in to_delete:
        state.pop(ip, None)
        meta.pop(ip, None)

    def build(ip: str) -> dict[str, Any]:
        m = meta.get(ip, {})
        return {
            "ip": ip,
            "country": m.get("country"),
            "country_code": m.get("country_code"),
        }
    
    new_ips.sort(key=lambda ip: state[ip]["last_seen"], reverse=True)
    returning_ips.sort(key=lambda ip: state[ip]["last_seen"], reverse=True)
    new = [build(ip) for ip in new_ips]
    returning = [build(ip) for ip in returning_ips]

    return new, returning

