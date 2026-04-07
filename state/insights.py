"""Track new and returning IPs with minimal state."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, TypedDict


class InsightStateItem(TypedDict):
    """State for an IP address."""
    first_seen: date
    last_seen: date
    seen_days: set[date]


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
    today = now.date()

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

    for ip in ips:
        if ip not in state:
            state[ip] = {
                "first_seen": today,
                "last_seen": today,
                "seen_days": {today},
            }
        else:
            item = state[ip]
            item["last_seen"] = today
            item.setdefault("seen_days", set()).add(today)

    cutoff = today - timedelta(days=30)

    to_delete = []

    for ip, item in state.items():
        days = item["seen_days"]
        new_days = {d for d in days if d >= cutoff}
        item["seen_days"] = new_days

        if not new_days:
            to_delete.append(ip)

    for ip in to_delete:
        state.pop(ip, None)
    
    new_ips = []
    returning_ips = []

    for ip, item in state.items():
        if item["last_seen"] != today:
            continue

        days_seen = len(item["seen_days"])

        if days_seen == 1:
            new_ips.append(ip)
        elif 2 <= days_seen <= 3:
            returning_ips.append(ip)

    def build(ip: str) -> dict[str, Any]:
        m = meta.get(ip, {})
        s = state[ip]

        days_seen = len(s["seen_days"])

        return {
            "ip": ip,
            "country": m.get("country"),
            "country_code": m.get("country_code"),
            "first_seen": s["first_seen"],
            "last_seen": s["last_seen"],
            "days_seen": days_seen,
        }
    
    new_ips.sort(key=lambda ip: state[ip]["last_seen"], reverse=True)
    returning_ips.sort(key=lambda ip: state[ip]["last_seen"], reverse=True)
    new = [build(ip) for ip in new_ips]
    returning = [build(ip) for ip in returning_ips]

    return new, returning

