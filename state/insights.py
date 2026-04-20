"""Track new and seen-before IPs using epoch timestamps and bitmask."""

from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict

import pycountry


class InsightStateItem(TypedDict):
    """State for an entry.

    l: last_seen_day (epoch day)
    m: 30-day activity bitmask (bit 0 = today)
    """
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

def process_insights(
    items: list[dict[str, Any]],
    insights: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Process snapshot and return new insights entries."""

    def update_dimension(
        values: set[str],
        state: dict[str, dict[str, int]],
    ) -> None:
        today_day = now.date().toordinal()

        # 1. Age all entries
        for item in state.values():
            delta = today_day - item["l"]

            if delta >= 30:
                item["m"] = 0
            elif delta > 0:
                item["m"] <<= delta
                item["m"] &= (1 << 30) - 1
                item["l"] = today_day

        # 2. Apply today's observations
        for value in values:
            if value not in state:
                state[value] = {"l": today_day, "m": 1}
                continue

            item = state[value]
            item["m"] |= 1
            item["l"] = today_day

        # 3. Prune
        to_delete = [k for k, v in state.items() if v["m"] == 0]
        for k in to_delete:
            del state[k]

    # ensure structure
    countries_state = insights.setdefault("countries", {})
    providers_state = insights.setdefault("providers", {})
    ports_state = insights.setdefault("ports", {})
    apps_state = insights.setdefault("applications", {})

    countries: set[str] = set()
    providers: set[str] = set()
    ports: set[str] = set()
    apps: set[str] = set()

    for item in items:
        if not isinstance(item, dict):
            continue

        if item.get("service_scope") != "PUBLIC":
            continue

        cc = item.get("country_code")
        if isinstance(cc, str) and cc:
            countries.add(cc)

        ao = item.get("asn_org")
        if isinstance(ao, str) and ao:
            providers.add(ao)

        port = item.get("port")
        if isinstance(port, int):
            ports.add(str(port))

        app = item.get("process_name")
        if isinstance(app, str) and app:
            apps.add(app)

    update_dimension(countries, countries_state)
    update_dimension(providers, providers_state)
    update_dimension(ports, ports_state)
    update_dimension(apps, apps_state)

    def build_new(state: dict[str, dict[str, int]], category: str) -> list[dict[str, Any]]:
        items = []
        for k, v in state.items():
            if v["m"] != 1:
                continue

            if category == "countries":
                try:
                    country = pycountry.countries.get(alpha_2=k.upper())
                    name = country.name if country else k
                except Exception:
                    name = k
                items.append({"value": k, "name": name})
            else:
                items.append({"value": k})

        return items

    def build_top(
        state: dict[str, dict[str, int]],
        category: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        items = []

        for k, v in state.items():
            score = v["m"].bit_count()
            if score == 0:
                continue

            items.append((k, score))

        # sort descending by score
        items.sort(key=lambda x: x[1], reverse=True)

        result = []
        for k, _ in items[:limit]:
            if category == "countries":
                try:
                    country = pycountry.countries.get(alpha_2=k.upper())
                    name = country.name if country else k
                except Exception:
                    name = k
                result.append({"value": k, "name": name})
            else:
                result.append({"value": k})

        return result

    new = {
        "countries": build_new(countries_state, "countries"),
        "providers": build_new(providers_state, "providers"),
        "ports": build_new(ports_state, "ports"),
        "applications": build_new(apps_state, "applications"),
    }

    top = {
        "countries": build_top(countries_state, "countries"),
        "providers": build_top(providers_state, "providers"),
        "ports": build_top(ports_state, "ports"),
        "applications": build_top(apps_state, "applications"),
    }

    return {
        "new": new,
        "top": top,
    }
