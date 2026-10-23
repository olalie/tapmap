"""Track new and seen-before IPs using epoch timestamps and bitmask."""

from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict

import pycountry

HISTORY_WINDOW_DAYS = 30


class InsightStateItem(TypedDict):
    """State for an entry.

    l: anchor_day (bitmap reference; bit i = observed on day l - i)
    m: 30-day activity bitmask (bit 0 = today, bit 29 = oldest retained day)
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


class EntryHistory(TypedDict):
    """Recorded activity within a 30-day window.

    last_seen_day and first_seen_day are date ordinals within the window.
    days contains 30 flags, oldest first; the last flag is the window's final day.
    """
    last_seen_day: int
    first_seen_day: int
    active_days: int
    days: list[bool]

def process_insights(
    items: list[dict[str, Any]],
    insights: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Process items, update insights in place, and return the top entries per dimension.

    Caller must supply only mapped PUBLIC connections; no scope filtering is
    applied here.
    """

    def update_dimension(
        values: set[str],
        state: dict[str, dict[str, int]],
    ) -> None:
        """Age entries, apply current observations, and prune zeroed entries.

        Postconditions: all surviving entries have l == today_day and m > 0.
        """
        today_day = now.date().toordinal()

        # 1. Age all entries
        for item in state.values():
            anchor_day = item["l"]
            delta = today_day - anchor_day

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

        cc = item.get("country_code")
        if isinstance(cc, str) and cc:
            countries.add(cc)

        ao = item.get("asn_org")
        if isinstance(ao, str) and ao:
            providers.add(ao)

        port = item.get("port")
        if isinstance(port, int):
            ports.add(str(port))

        app = item.get("app_name")
        if isinstance(app, str) and app:
            apps.add(app)

    update_dimension(countries, countries_state)
    update_dimension(providers, providers_state)
    update_dimension(ports, ports_state)
    update_dimension(apps, apps_state)

    def build_top(
        state: dict[str, dict[str, int]],
        category: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return top entries ranked by bit_count; all entries tied at the cutoff are included."""
        items = []

        for k, v in state.items():
            score = v["m"].bit_count()
            if score == 0:
                continue

            items.append((k, score))

        # sort descending by score, selection uses cutoff
        items.sort(key=lambda x: x[1], reverse=True)

        if len(items) <= limit:
            selected = items
        else:
            cutoff = items[limit - 1][1]
            selected = [x for x in items if x[1] >= cutoff]

        result = []
        for k, _ in selected:
            if category == "countries":
                result.append({"value": k, "name": country_name(k)})
            else:
                result.append({"value": k})

        return result

    top = {
        "countries": build_top(countries_state, "countries"),
        "providers": build_top(providers_state, "providers"),
        "ports": build_top(ports_state, "ports"),
        "applications": build_top(apps_state, "applications"),
    }

    return {
        "top": top,
    }


def country_name(code: str) -> str:
    """Return the country name for an alpha-2 code.

    Return the code itself if it is unknown or the lookup fails.
    """
    try:
        country = pycountry.countries.get(alpha_2=code.upper())
        return country.name if country else code
    except Exception:
        return code


def last_seen_day(entry: Any) -> int | None:
    """Return the latest observation day of an {l, m} entry.

    Return None if the entry is not a dict, l or m is not an int, or m is 0.
    """
    if not isinstance(entry, dict):
        return None
    anchor_day = entry.get("l")
    mask = entry.get("m")
    if not isinstance(anchor_day, int) or not isinstance(mask, int) or mask == 0:
        return None
    lowest_set_bit_position = (mask & -mask).bit_length() - 1
    return anchor_day - lowest_set_bit_position


def entry_history(entry: Any, today_day: int) -> EntryHistory | None:
    """Return an entry's recorded activity within the 30 days ending on today_day.

    l is the anchor day's ordinal; bit i of m represents day l - i.
    The anchor may precede today_day if the entry has not been updated today.
    Return None if the entry is not a dict, l or m is not an int, or no activity
    falls within the window.
    """
    if not isinstance(entry, dict):
        return None
    anchor_day = entry.get("l")
    mask = entry.get("m")
    if not isinstance(anchor_day, int) or not isinstance(mask, int):
        return None

    window_start_day = today_day - (HISTORY_WINDOW_DAYS - 1)
    active_day_list = [
        day
        for day in range(window_start_day, today_day + 1)
        if 0 <= anchor_day - day < HISTORY_WINDOW_DAYS and (mask >> (anchor_day - day)) & 1
    ]
    if not active_day_list:
        return None

    active_day_set = set(active_day_list)
    return EntryHistory(
        last_seen_day=active_day_list[-1],
        first_seen_day=active_day_list[0],
        active_days=len(active_day_list),
        days=[day in active_day_set for day in range(window_start_day, today_day + 1)],
    )


def distinct_active_days(insights: dict[str, Any]) -> int:
    """Return the number of distinct active days in the 30-day Insights history."""
    combined = 0
    for dimension in insights.values():
        if not isinstance(dimension, dict):
            continue
        for entry in dimension.values():
            if not isinstance(entry, dict):
                continue
            mask = entry.get("m")
            if isinstance(mask, int):
                combined |= mask
    return combined.bit_count()
