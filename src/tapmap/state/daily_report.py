"""Daily activity report analytics for TapMap.

Pure computation layer: insights data in → DailyReportData out.
No Dash, no Plotly, no I/O.
"""

from __future__ import annotations

from typing import Any, TypedDict

NUMBER_WORDS = {
    0: "zero",
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
}

MIN_RELIABLE_HISTORY_DAYS = 7
HISTORY_WINDOW_DAYS = 30
MIN_APPENDIX_HISTORY_DAYS = 8

OCCASIONAL_RATIO = 8 / 30
STABLE_RATIO = 21 / 30
STABLE_ACTIVITY_THRESHOLD = 0.70
VARIABLE_ACTIVITY_THRESHOLD = 0.45
PROVIDER_HIGH_CONCENTRATION_THRESHOLD = 0.10
PROVIDER_MODERATE_CONCENTRATION_THRESHOLD = 0.25

# One per recurrence category: (category_name, example_name_or_None, day_strip_or_None)
RecurrenceExample = tuple[str, str | None, list[bool] | None]


class ProviderConcentration(TypedDict):
    """Provider concentration metrics."""

    total_providers: int
    cumulative_pcts: list[float]


class CountryMapPoint(TypedDict):
    """Geographical point for a country on the activity map."""

    lat: float
    lon: float
    active_days: int
    code: str


class DailyReportData(TypedDict):
    """Aggregated data for the daily activity report."""

    history_days: int
    intro_text: str
    today_text: str
    activity_pattern_text: str
    # applications
    application_total: int
    application_counts: dict[str, int]
    recurrence_labels: dict[str, str]
    recurrence_examples: list[RecurrenceExample]
    applications_summary: str
    # providers
    provider_concentration: ProviderConcentration
    providers_summary: str
    # countries
    country_total: int
    countries_summary: str
    country_map_points: list[CountryMapPoint]


def format_count(value: int) -> str:
    """Return human-readable count string."""
    return NUMBER_WORDS.get(value, str(value))


def count_history_days(bitmask: int) -> int:
    """Return observed history length from leftmost set bit."""
    return bitmask.bit_length()


def get_max_history_days(insights: dict[str, Any]) -> int:
    """Return maximum observed history across all insight categories."""
    categories = ["countries", "providers", "ports", "applications"]
    max_days = 0
    for category in categories:
        for item in insights.get(category, {}).values():
            bitmask = item.get("m")
            if isinstance(bitmask, int):
                max_days = max(max_days, count_history_days(bitmask))
    return max_days


def count_new_today(state: dict[str, dict[str, Any]]) -> int:
    """Return number of entries observed for the first time today."""
    return sum(1 for item in state.values() if item.get("m") == 1)


def classify_recurrence(active_days: int, history_days: int) -> str:
    """Return recurrence category from active day count."""
    if active_days == 1:
        return "Seen once"
    ratio = active_days / history_days
    if ratio < OCCASIONAL_RATIO:
        return "Occasional"
    if ratio < STABLE_RATIO:
        return "Recurring"
    return "Stable"


def build_recurrence_labels(history_days: int) -> dict[str, str]:
    """Return display labels derived from actual category bins."""
    bins: dict[str, list[int]] = {
        cat: [] for cat in ("Stable", "Recurring", "Occasional", "Seen once")
    }
    for d in range(1, history_days + 1):
        bins[classify_recurrence(d, history_days)].append(d)
    labels: dict[str, str] = {}
    for cat, days in bins.items():
        if not days:
            labels[cat] = cat
        elif days[0] == days[-1]:
            n = days[0]
            labels[cat] = f"{cat} ({n} day{'s' if n > 1 else ''})"
        else:
            labels[cat] = f"{cat} ({days[0]}\u2013{days[-1]} days)"
    return labels


def build_recurrence_counts(
    state: dict[str, dict[str, Any]],
    history_days: int = HISTORY_WINDOW_DAYS,
) -> dict[str, int]:
    """Return recurrence category counts."""
    counts: dict[str, int] = {
        "Stable": 0,
        "Recurring": 0,
        "Occasional": 0,
        "Seen once": 0,
    }
    for item in state.values():
        bitmask = item.get("m")
        if not isinstance(bitmask, int):
            continue
        active_days = bitmask.bit_count()
        if active_days == 0:
            continue
        counts[classify_recurrence(active_days, history_days)] += 1
    return counts


def build_recurrence_examples(
    state: dict[str, dict[str, Any]],
    history_days: int,
) -> list[RecurrenceExample]:
    """Return one (category, name, day-strip) per recurrence category."""
    categories = ["Stable", "Recurring", "Occasional", "Seen once"]
    found: dict[str, tuple[str, int] | None] = {cat: None for cat in categories}
    for name, item in state.items():
        bitmask = item.get("m")
        if not isinstance(bitmask, int) or bitmask.bit_count() == 0:
            continue
        cat = classify_recurrence(bitmask.bit_count(), history_days)
        if found[cat] is None:
            found[cat] = (name, bitmask)
        if all(v is not None for v in found.values()):
            break
    result: list[RecurrenceExample] = []
    for cat in categories:
        entry = found[cat]
        if entry is None:
            result.append((cat, None, None))
        else:
            name, bitmask = entry
            days = [
                bool((bitmask >> i) & 1)
                for i in range(HISTORY_WINDOW_DAYS - 1, -1, -1)
            ]
            result.append((cat, name, days))
    return result


def build_today_text(insights: dict[str, Any]) -> str:
    """Return summary of newly observed activity today."""
    new_items = [
        {
            "count": count_new_today(insights.get("applications", {})),
            "singular": "app",
            "plural": "apps",
        },
        {
            "count": count_new_today(insights.get("providers", {})),
            "singular": "provider",
            "plural": "providers",
        },
        {
            "count": count_new_today(insights.get("countries", {})),
            "singular": "country",
            "plural": "countries",
        },
    ]
    total_new = sum(item["count"] for item in new_items)

    if total_new == 0:
        return "No new apps, providers or countries appeared today."

    active = [item for item in new_items if item["count"] > 0]
    parts = [
        (
            f"{format_count(item['count'])} new "
            f"{item['singular'] if item['count'] == 1 else item['plural']}"
        )
        for item in active
    ]
    parts[0] = parts[0].capitalize()

    if len(parts) == 1:
        summary = parts[0]
    elif len(parts) == 2:
        summary = f"{parts[0]} and {parts[1]}"
    else:
        summary = f"{', '.join(parts[:-1])} and {parts[-1]}"

    return f"{summary} appeared today. See details in the Insights panel."


def compute_activity_days_fraction(
    state: dict[str, dict[str, Any]],
    history_days: int,
) -> float:
    """Return fraction of total entity-days from Stable+Recurring entities."""
    recurring_days = 0
    total_days = 0
    for item in state.values():
        bitmask = item.get("m")
        if not isinstance(bitmask, int):
            continue
        active = bitmask.bit_count()
        if active == 0:
            continue
        total_days += active
        if classify_recurrence(active, history_days) in ("Stable", "Recurring"):
            recurring_days += active
    return recurring_days / total_days if total_days > 0 else 0.0


def build_activity_pattern(
    app_state: dict[str, dict[str, Any]],
    country_state: dict[str, dict[str, Any]],
    history_days: int,
) -> str:
    """Return global behavioral pattern summary, or empty string if insufficient history."""
    if history_days < MIN_RELIABLE_HISTORY_DAYS:
        return ""
    app_fraction = compute_activity_days_fraction(app_state, history_days)
    country_fraction = compute_activity_days_fraction(country_state, history_days)
    app_has_activity = any(
        isinstance(item.get("m"), int) and item["m"].bit_count() > 0
        for item in app_state.values()
    )
    country_has_activity = any(
        isinstance(item.get("m"), int) and item["m"].bit_count() > 0
        for item in country_state.values()
    )
    if app_has_activity and country_has_activity:
        core_fraction = (app_fraction + country_fraction) / 2
    elif app_has_activity:
        core_fraction = app_fraction
    elif country_has_activity:
        core_fraction = country_fraction
    else:
        core_fraction = 0.0
    if core_fraction >= STABLE_ACTIVITY_THRESHOLD:
        return (
            "Most activity-days came from recurring connections."
        )
    if core_fraction < VARIABLE_ACTIVITY_THRESHOLD:
        return (
            "Short-lived connections made up a larger share across the period."
        )
    return (
        "Recurring and short-lived connections appeared throughout the period."
    )


def build_intro_text(history_days: int) -> str:
    """Return summary of available connection history."""
    history_days_text = format_count(history_days)
    if history_days < MIN_RELIABLE_HISTORY_DAYS:
        day_label = (
            "one day"
            if history_days == 1
            else f"the last {history_days_text} days"
        )
        return (
            f"TapMap currently has connection data from only {day_label}. "
            "The report will become more reliable with more history."
        )
    if history_days >= HISTORY_WINDOW_DAYS:
        return "TapMap is currently using a rolling 30-day activity window."
    return f"TapMap now has {history_days_text} days of connection history."


def build_applications_summary(
    application_total: int,
    counts: dict[str, int],
) -> str:
    """Return applications summary text."""
    if application_total == 0:
        return "No applications used the internet during this period."

    application_label = "application" if application_total == 1 else "applications"
    application_total_text = format_count(application_total)
    frequent = counts["Stable"] + counts["Recurring"]
    transient = counts["Occasional"] + counts["Seen once"]
    seen_once = counts["Seen once"]
    total = frequent + transient
    fraction = frequent / total if total > 0 else 0.0

    once_phrase = ""
    if 2 <= seen_once <= 5:
        once_phrase = ", and some only once"
    elif seen_once >= 6:
        once_phrase = ", and many only once"

    if frequent == 0:
        distribution_text = (
            f"Most apps appeared briefly{once_phrase}."
        )
    elif transient == 0:
        distribution_text = (
            "Apps appeared repeatedly during the period."
        )
    elif fraction < 0.33:
        distribution_text = (
            f"Most apps appeared briefly{once_phrase}. "
            "Some appeared repeatedly during the period."
        )
    elif fraction <= 0.66:
        distribution_text = (
            "Some apps appeared repeatedly during the period. "
            "Many others appeared briefly."
        )
    else:
        distribution_text = (
            "Many apps appeared repeatedly during the period. "
            "Others appeared briefly."
        )

    return (
        f"{application_total_text.capitalize()} "
        f"{application_label} used the internet during this period. "
        "Some were applications you used directly. "
        f"Others were background services running on your system. "
        f"{distribution_text}"
    )


def build_provider_concentration(
    state: dict[str, dict[str, Any]],
) -> ProviderConcentration:
    """Return sorted cumulative activity percentages for provider concentration curve."""
    provider_days = sorted(
        (
            item["m"].bit_count()
            for item in state.values()
            if isinstance(item.get("m"), int) and item["m"].bit_count() > 0
        ),
        reverse=True,
    )
    if not provider_days:
        return ProviderConcentration(total_providers=0, cumulative_pcts=[])
    total_days = sum(provider_days)
    cumulative = 0
    cumulative_pcts: list[float] = []
    for days in provider_days:
        cumulative += days
        cumulative_pcts.append(cumulative / total_days * 100)
    return ProviderConcentration(
        total_providers=len(provider_days),
        cumulative_pcts=cumulative_pcts,
    )


def build_providers_summary(concentration: ProviderConcentration) -> str:
    """Return providers concentration summary text."""
    total = concentration["total_providers"]
    if total == 0:
        return "No provider activity was recorded during this period."
    total_text = format_count(total)
    provider_label = "provider" if total == 1 else "providers"
    return (
        f"{total_text.capitalize()} {provider_label} were observed. "
        "These are the network operators at the destinations used by your applications. "
        "A single app may use several."
    )


def build_providers_concentration_narrative(concentration: ProviderConcentration) -> str:
    """Return narrative sentence describing provider concentration."""
    total = concentration["total_providers"]
    if total == 0:
        return ""
    if total == 1:
        return (
            "Most observed activity was handled by "
            "a relatively small group of providers."
        )
    cumulative_pcts = concentration["cumulative_pcts"]
    top_50_count = next(
        (i + 1 for i, pct in enumerate(cumulative_pcts) if pct >= 50.0),
        total,
    )
    provider_50_fraction = top_50_count / total
    if provider_50_fraction <= PROVIDER_HIGH_CONCENTRATION_THRESHOLD:
        return (
            "Most activity came through a few providers."
        )
    if provider_50_fraction <= PROVIDER_MODERATE_CONCENTRATION_THRESHOLD:
        return (
            "At least half of the activity came through a few providers."
        )
    return "Activity was spread across many providers."


def build_countries_summary(country_total: int) -> str:
    """Return countries summary text."""
    country_total_text = format_count(country_total)
    return (
        f"Applications on your computer connected to systems "
        f"in {country_total_text} different countries."
    )


def _build_country_map_points(
    country_state: dict[str, dict[str, Any]],
) -> list[CountryMapPoint]:
    """Return map point data for all observed countries with known centroids."""
    from tapmap.ui.country_centers import get_center  # deferred to avoid import cycle

    points: list[CountryMapPoint] = []
    for code, item in country_state.items():
        try:
            lat, lon = get_center(code)
        except KeyError:
            continue
        bitmask = item.get("m", 0)
        active_days = bitmask.bit_count() if isinstance(bitmask, int) else 0
        if active_days == 0:
            continue
        points.append(CountryMapPoint(lat=lat, lon=lon, active_days=active_days, code=code))
    return points


def build_report_data(insights: dict[str, Any]) -> DailyReportData:
    """Compute DailyReportData from the insights state."""
    history_days = get_max_history_days(insights)

    app_state = insights.get("applications", {})
    country_state = insights.get("countries", {})
    provider_state = insights.get("providers", {})

    recurrence_labels = build_recurrence_labels(history_days)
    application_counts = build_recurrence_counts(app_state, history_days)
    application_total = sum(application_counts.values())

    concentration = build_provider_concentration(provider_state)
    providers_narrative = build_providers_concentration_narrative(concentration)
    providers_full_summary = (
        build_providers_summary(concentration)
        + (f" {providers_narrative}" if providers_narrative else "")
    )

    country_counts = build_recurrence_counts(country_state, history_days)
    country_total = sum(country_counts.values())

    return DailyReportData(
        history_days=history_days,
        intro_text=build_intro_text(history_days),
        today_text=build_today_text(insights),
        activity_pattern_text=build_activity_pattern(app_state, country_state, history_days),
        application_total=application_total,
        application_counts=application_counts,
        recurrence_labels=recurrence_labels,
        recurrence_examples=build_recurrence_examples(app_state, history_days),
        applications_summary=build_applications_summary(application_total, application_counts),
        provider_concentration=concentration,
        providers_summary=providers_full_summary,
        country_total=country_total,
        countries_summary=build_countries_summary(country_total),
        country_map_points=_build_country_map_points(country_state),
    )
