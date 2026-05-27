"""Unit tests for state.daily_report pure analytics functions."""

from __future__ import annotations

from tapmap.state.daily_report import (
    HISTORY_WINDOW_DAYS,
    MIN_RELIABLE_HISTORY_DAYS,
    ProviderConcentration,
    build_activity_pattern,
    build_applications_summary,
    build_countries_summary,
    build_intro_text,
    build_provider_concentration,
    build_providers_concentration_narrative,
    build_providers_summary,
    build_recurrence_counts,
    build_recurrence_examples,
    build_recurrence_labels,
    build_report_data,
    build_today_text,
    classify_recurrence,
    compute_activity_days_fraction,
    count_history_days,
    count_new_today,
    format_count,
    get_max_history_days,
)

# --- format_count ---


def test_format_count_returns_word_for_values_in_dict() -> None:
    """Return English words for values 0 through 10."""
    assert format_count(0) == "zero"
    assert format_count(1) == "one"
    assert format_count(10) == "ten"


def test_format_count_returns_string_for_values_outside_dict() -> None:
    """Return the numeric string for values above ten."""
    assert format_count(11) == "11"
    assert format_count(100) == "100"


# --- count_history_days ---


def test_count_history_days_returns_bit_length_of_bitmask() -> None:
    """Return the bit length of the supplied bitmask."""
    assert count_history_days(1) == 1
    assert count_history_days(0b11111) == 5
    assert count_history_days((1 << 30) - 1) == 30


# --- get_max_history_days ---


def test_get_max_history_days_returns_zero_for_empty_insights() -> None:
    """Return 0 when the insights dict has no entries."""
    assert get_max_history_days({}) == 0


def test_get_max_history_days_finds_maximum_across_all_categories() -> None:
    """Return the longest bitmask length across all four categories."""
    insights = {
        "applications": {"App": {"m": (1 << 20) - 1}},   # bit_length=20
        "countries":    {"US":  {"m": (1 << 30) - 1}},   # bit_length=30
        "providers":    {"P1":  {"m": (1 << 10) - 1}},   # bit_length=10
        "ports":        {"443": {"m": (1 << 15) - 1}},   # bit_length=15
    }
    assert get_max_history_days(insights) == 30


def test_get_max_history_days_skips_missing_and_non_int_bitmask() -> None:
    """Skip entries with no 'm' key or a non-integer bitmask."""
    insights = {
        "applications": {
            "AppA": {},               # no 'm' key
            "AppB": {"m": "bad"},     # non-int
            "AppC": {"m": (1 << 7) - 1},  # valid, bit_length=7
        }
    }
    assert get_max_history_days(insights) == 7


# --- count_new_today ---


def test_count_new_today_returns_zero_for_empty_state() -> None:
    """Return 0 for an empty state dict."""
    assert count_new_today({}) == 0


def test_count_new_today_counts_only_entries_with_m_equal_to_one() -> None:
    """Count only items first observed today (m == 1)."""
    state = {
        "new1": {"m": 1},
        "new2": {"m": 1},
        "old1": {"m": 0b11},   # active 2 days, not new
        "old2": {"m": 0},      # zeroed
    }
    assert count_new_today(state) == 2


# --- classify_recurrence ---


def test_classify_recurrence_returns_seen_once_for_single_active_day() -> None:
    """Return 'Seen once' when active_days is 1, regardless of history length."""
    assert classify_recurrence(1, 1) == "Seen once"
    assert classify_recurrence(1, 30) == "Seen once"


def test_classify_recurrence_occasional_below_lower_boundary() -> None:
    """Return 'Occasional' when the ratio is strictly below OCCASIONAL_RATIO."""
    # 7/30 < 8/30 → Occasional; 2/30 < 8/30 → Occasional
    assert classify_recurrence(7, 30) == "Occasional"
    assert classify_recurrence(2, 30) == "Occasional"


def test_classify_recurrence_recurring_at_lower_boundary() -> None:
    """Return 'Recurring' when the ratio exactly equals OCCASIONAL_RATIO."""
    # 8/30 == OCCASIONAL_RATIO, not strictly less → Recurring
    assert classify_recurrence(8, 30) == "Recurring"


def test_classify_recurrence_recurring_below_stable_boundary() -> None:
    """Return 'Recurring' when the ratio is below STABLE_RATIO."""
    assert classify_recurrence(20, 30) == "Recurring"


def test_classify_recurrence_stable_at_lower_boundary() -> None:
    """Return 'Stable' when the ratio exactly equals STABLE_RATIO."""
    # 21/30 == STABLE_RATIO, not strictly less → Stable
    assert classify_recurrence(21, 30) == "Stable"


def test_classify_recurrence_stable_at_full_history() -> None:
    """Return 'Stable' when active for the full history window."""
    assert classify_recurrence(30, 30) == "Stable"


# --- build_recurrence_labels ---


def test_build_recurrence_labels_full_history_produces_bounded_labels() -> None:
    """Return labels with exact day ranges for all four categories."""
    labels = build_recurrence_labels(HISTORY_WINDOW_DAYS)

    assert labels["Stable"] == "Stable (21\u201330 days)"
    assert labels["Recurring"] == "Recurring (8\u201320 days)"
    assert labels["Occasional"] == "Occasional (2\u20137 days)"
    assert labels["Seen once"] == "Seen once (1 day)"


def test_build_recurrence_labels_short_history_empty_bins_use_category_name() -> None:
    """Use the plain category name for bins that have no values."""
    # With history_days=1, only 'Seen once' is reachable.
    labels = build_recurrence_labels(1)

    assert labels["Seen once"] == "Seen once (1 day)"
    assert labels["Stable"] == "Stable"
    assert labels["Recurring"] == "Recurring"
    assert labels["Occasional"] == "Occasional"


# --- build_recurrence_counts ---


def test_build_recurrence_counts_returns_all_zeros_for_empty_state() -> None:
    """Return zero counts when the state is empty."""
    counts = build_recurrence_counts({})
    assert counts == {"Stable": 0, "Recurring": 0, "Occasional": 0, "Seen once": 0}


def test_build_recurrence_counts_skips_zero_and_non_int_bitmasks() -> None:
    """Skip entries with a zero bitmask, missing key, or non-integer value."""
    state = {
        "a": {"m": 0},
        "b": {"m": "bad"},
        "c": {},
    }
    assert sum(build_recurrence_counts(state, history_days=30).values()) == 0


def test_build_recurrence_counts_classifies_items_correctly() -> None:
    """Place each item into the correct recurrence bucket."""
    # With history_days=30: 1→Seen once, 4→Occasional, 12→Recurring, 25→Stable
    state = {
        "seen_once":  {"m": 1},
        "occasional": {"m": (1 << 4) - 1},    # bit_count=4
        "recurring":  {"m": (1 << 12) - 1},   # bit_count=12
        "stable":     {"m": (1 << 25) - 1},   # bit_count=25
    }
    counts = build_recurrence_counts(state, history_days=30)

    assert counts["Seen once"] == 1
    assert counts["Occasional"] == 1
    assert counts["Recurring"] == 1
    assert counts["Stable"] == 1


# --- build_recurrence_examples ---


def test_build_recurrence_examples_returns_none_tuple_for_missing_category() -> None:
    """Return (category, None, None) for categories with no matching items."""
    state = {"AppStable": {"m": (1 << 25) - 1}}   # 25 active days → Stable
    examples = build_recurrence_examples(state, history_days=30)

    by_cat = {cat: (name, days) for cat, name, days in examples}

    assert by_cat["Stable"][0] == "AppStable"
    assert by_cat["Stable"][1] is not None
    assert by_cat["Recurring"] == (None, None)
    assert by_cat["Occasional"] == (None, None)
    assert by_cat["Seen once"] == (None, None)


def test_build_recurrence_examples_day_strip_matches_bitmask() -> None:
    """Verify the day-strip boolean list mirrors the bitmask bit pattern."""
    # m=0b111: bits 0, 1, 2 set → last three positions active
    state = {"App": {"m": 0b111}}   # bit_count=3 → Occasional with history=30
    examples = build_recurrence_examples(state, history_days=30)

    by_cat = {cat: days for cat, _, days in examples}
    strip = by_cat["Occasional"]

    assert strip is not None
    assert len(strip) == HISTORY_WINDOW_DAYS
    assert strip[:27] == [False] * 27
    assert strip[27:] == [True, True, True]


# --- compute_activity_days_fraction ---


def test_compute_activity_days_fraction_returns_zero_for_empty_state() -> None:
    """Return 0.0 when the state is empty."""
    assert compute_activity_days_fraction({}, history_days=30) == 0.0


def test_compute_activity_days_fraction_all_stable_returns_one() -> None:
    """Return 1.0 when all entity-days come from Stable items."""
    state = {"App": {"m": (1 << 25) - 1}}   # 25 active days, Stable with history=30
    assert compute_activity_days_fraction(state, history_days=30) == 1.0


def test_compute_activity_days_fraction_all_transient_returns_zero() -> None:
    """Return 0.0 when all entity-days come from Occasional or Seen-once items."""
    state = {
        "a": {"m": 1},              # Seen once
        "b": {"m": (1 << 4) - 1},  # Occasional (4 active days, history=30)
    }
    assert compute_activity_days_fraction(state, history_days=30) == 0.0


# --- build_activity_pattern ---


def test_build_activity_pattern_returns_empty_below_min_history() -> None:
    """Return an empty string when history is below the reliability threshold."""
    result = build_activity_pattern({}, {}, history_days=MIN_RELIABLE_HISTORY_DAYS - 1)
    assert result == ""


def test_build_activity_pattern_stable_narrative() -> None:
    """Return the stable narrative when most activity is recurring."""
    # All-Stable apps and countries → core_fraction = 1.0 ≥ STABLE_ACTIVITY_THRESHOLD
    stable_state = {"a": {"m": (1 << 25) - 1}}
    result = build_activity_pattern(stable_state, stable_state, history_days=30)
    assert "recurring connections" in result.lower()


def test_build_activity_pattern_variable_narrative() -> None:
    """Return the variable narrative when most activity is intermittent."""
    # All-Seen-once → core_fraction = 0.0 < VARIABLE_ACTIVITY_THRESHOLD
    transient_state = {"a": {"m": 1}}
    result = build_activity_pattern(transient_state, transient_state, history_days=30)
    assert "short-lived" in result.lower()


def test_build_activity_pattern_uses_non_empty_dimension_only() -> None:
    """Use the available dimension when the other has no active entities."""
    # All-Stable apps, empty country state → core_fraction uses apps only.
    stable_state = {"a": {"m": (1 << 25) - 1}}
    result = build_activity_pattern(stable_state, {}, history_days=30)
    assert "recurring connections" in result.lower()


# --- build_intro_text ---


def test_build_intro_text_single_day() -> None:
    """Use the 'one day' phrasing for exactly one day of history."""
    result = build_intro_text(1)
    assert "one day" in result
    assert "reliable" in result


def test_build_intro_text_sparse_history() -> None:
    """Report the word-form count for sparse history below the threshold."""
    result = build_intro_text(3)
    assert "three" in result
    assert "reliable" in result


def test_build_intro_text_partial_window() -> None:
    """Report the numeric day count when history is a partial window."""
    result = build_intro_text(15)
    assert "15" in result   # NUMBER_WORDS only covers 0-10
    assert "rolling" not in result


def test_build_intro_text_full_window() -> None:
    """Report the rolling window when at the full 30-day limit."""
    result = build_intro_text(HISTORY_WINDOW_DAYS)
    assert "rolling" in result
    assert "30-day" in result


# --- build_applications_summary ---


def test_build_applications_summary_mostly_transient() -> None:
    """Use the 'briefly' phrasing when most apps are occasional."""
    counts = {"Stable": 0, "Recurring": 0, "Occasional": 3, "Seen once": 1}
    result = build_applications_summary(4, counts)
    assert "briefly" in result


def test_build_applications_summary_no_consistent_phrase_when_no_frequent() -> None:
    """Do not mention consistent usage when Stable+Recurring is zero."""
    counts = {"Stable": 0, "Recurring": 0, "Occasional": 2, "Seen once": 3}
    result = build_applications_summary(5, counts)
    assert "ran consistently throughout the period" not in result


def test_build_applications_summary_no_transient_phrase_when_no_transient() -> None:
    """Do not mention occasional/brief usage when transient categories are zero."""
    counts = {"Stable": 2, "Recurring": 1, "Occasional": 0, "Seen once": 0}
    result = build_applications_summary(3, counts)
    assert "occasionally or briefly" not in result


def test_build_applications_summary_zero_total_has_dedicated_message() -> None:
    """Use a neutral message when no applications were observed."""
    counts = {"Stable": 0, "Recurring": 0, "Occasional": 0, "Seen once": 0}
    result = build_applications_summary(0, counts)
    assert result == "No applications used the internet during this period."


def test_build_applications_summary_mixed() -> None:
    """Use the 'Some apps' phrasing for an even split."""
    counts = {"Stable": 1, "Recurring": 0, "Occasional": 1, "Seen once": 0}
    result = build_applications_summary(2, counts)
    assert "Some" in result


def test_build_applications_summary_mostly_recurring() -> None:
    """Use the 'Many apps' phrasing when most apps are recurring."""
    counts = {"Stable": 3, "Recurring": 0, "Occasional": 1, "Seen once": 0}
    result = build_applications_summary(4, counts)
    assert "Many" in result


def test_build_applications_summary_uses_singular_label_for_one_app() -> None:
    """Use 'application' (singular) before 'used' when total is one."""
    counts = {"Stable": 1, "Recurring": 0, "Occasional": 0, "Seen once": 0}
    result = build_applications_summary(1, counts)
    assert "One application used" in result


# --- build_provider_concentration ---


def test_build_provider_concentration_empty_state() -> None:
    """Return zero total and empty percentages for an empty state."""
    result = build_provider_concentration({})
    assert result["total_providers"] == 0
    assert result["cumulative_pcts"] == []


def test_build_provider_concentration_single_provider_is_100_percent() -> None:
    """Return 100% for a single provider."""
    state = {"p1": {"m": (1 << 15) - 1}}
    result = build_provider_concentration(state)
    assert result["total_providers"] == 1
    assert result["cumulative_pcts"] == [100.0]


def test_build_provider_concentration_cumulative_percentages_descending_order() -> None:
    """Sort by activity descending and compute correct cumulative percentages."""
    # p1=20 active days, p2=10 active days → total=30
    state = {
        "p1": {"m": (1 << 20) - 1},   # bit_count=20
        "p2": {"m": (1 << 10) - 1},   # bit_count=10
    }
    result = build_provider_concentration(state)
    pcts = result["cumulative_pcts"]

    assert result["total_providers"] == 2
    assert abs(pcts[0] - 200 / 3) < 0.01   # 20/30 * 100 ≈ 66.67
    assert pcts[1] == 100.0


def test_build_provider_concentration_skips_zero_activity_entries() -> None:
    """Exclude providers with a zero bitmask."""
    state = {
        "active":   {"m": (1 << 10) - 1},
        "inactive": {"m": 0},
    }
    result = build_provider_concentration(state)
    assert result["total_providers"] == 1


# --- build_providers_summary ---


def test_build_providers_summary_no_providers() -> None:
    """Return a 'no activity' message when there are no providers."""
    result = build_providers_summary(
        ProviderConcentration(total_providers=0, cumulative_pcts=[])
    )
    assert "No provider activity" in result


def test_build_providers_summary_uses_singular_for_one_provider() -> None:
    """Use 'provider' (singular) when total is one."""
    result = build_providers_summary(
        ProviderConcentration(total_providers=1, cumulative_pcts=[100.0])
    )
    assert " provider " in result
    assert "providers" not in result


def test_build_providers_summary_uses_plural_for_multiple_providers() -> None:
    """Use 'providers' (plural) when total is more than one."""
    result = build_providers_summary(
        ProviderConcentration(total_providers=5, cumulative_pcts=[20.0] * 5)
    )
    assert "providers" in result


# --- build_providers_concentration_narrative ---


def test_concentration_narrative_returns_empty_for_no_providers() -> None:
    """Return an empty string when there are no providers."""
    result = build_providers_concentration_narrative(
        ProviderConcentration(total_providers=0, cumulative_pcts=[])
    )
    assert result == ""


def test_concentration_narrative_high_concentration() -> None:
    """Return the small-group narrative when one provider covers >50% of activity."""
    # top_50_count=1, total=10 → 1/10=0.10 ≤ HIGH_THRESHOLD
    result = build_providers_concentration_narrative(
        ProviderConcentration(
            total_providers=10,
            cumulative_pcts=[60.0] + [100.0] * 9,
        )
    )
    assert "few providers" in result.lower()


def test_concentration_narrative_single_provider_not_broad() -> None:
    """Avoid broad-range wording when only one provider is present."""
    result = build_providers_concentration_narrative(
        ProviderConcentration(total_providers=1, cumulative_pcts=[100.0])
    )
    assert "broad" not in result.lower()


def test_concentration_narrative_moderate_concentration() -> None:
    """Return the established-group narrative when a small set covers >50%."""
    # top_50_count=2, total=10 → 2/10=0.20, in (HIGH, MODERATE]
    result = build_providers_concentration_narrative(
        ProviderConcentration(
            total_providers=10,
            cumulative_pcts=[40.0, 70.0] + [100.0] * 8,
        )
    )
    assert "at least half" in result.lower()


def test_concentration_narrative_distributed() -> None:
    """Return the broad-range narrative when many providers share activity."""
    # top_50_count=4, total=10 → 4/10=0.40 > MODERATE_THRESHOLD
    result = build_providers_concentration_narrative(
        ProviderConcentration(
            total_providers=10,
            cumulative_pcts=[20.0, 35.0, 45.0, 60.0] + [100.0] * 6,
        )
    )
    assert "many providers" in result.lower()


# --- build_countries_summary ---


def test_build_countries_summary_singular() -> None:
    """Use the word 'one' for a single country."""
    result = build_countries_summary(1)
    assert "one" in result
    assert "countries" in result


def test_build_countries_summary_plural() -> None:
    """Use the numeric count when total is more than one."""
    result = build_countries_summary(5)
    assert "five" in result
    assert "countries" in result


# --- build_today_text ---


def test_build_today_text_no_new_activity() -> None:
    """Return a 'no new' message when all category counts are zero."""
    result = build_today_text({})
    assert "No new" in result


def test_build_today_text_single_category_new() -> None:
    """Format the message correctly for one category with new entries."""
    insights = {"applications": {"App": {"m": 1}}}
    result = build_today_text(insights)
    assert "One new app" in result
    assert "appeared today" in result


def test_build_today_text_two_categories_joined_with_and() -> None:
    """Join two active categories with 'and'."""
    insights = {
        "applications": {"App": {"m": 1}},
        "providers":    {"P1": {"m": 1}, "P2": {"m": 1}},
    }
    result = build_today_text(insights)
    assert "One new app" in result
    assert "two new providers" in result
    assert " and " in result
    assert "," not in result.split("appeared")[0]


def test_build_today_text_three_categories_uses_comma_and() -> None:
    """Join three active categories with commas and 'and' before the last."""
    insights = {
        "applications": {"App": {"m": 1}},
        "providers":    {"P1":  {"m": 1}},
        "countries":    {"US":  {"m": 1}},
    }
    result = build_today_text(insights)
    assert "One new app" in result
    assert "one new provider" in result
    assert "one new country" in result
    assert ", " in result


# --- build_report_data (integration) ---


def test_build_report_data_returns_all_required_keys() -> None:
    """Verify build_report_data returns a complete DailyReportData structure."""
    report = build_report_data({})
    required = {
        "history_days", "intro_text", "today_text", "activity_pattern_text",
        "application_total", "application_counts", "recurrence_labels",
        "recurrence_examples", "applications_summary",
        "provider_concentration", "providers_summary",
        "country_total", "countries_summary", "country_map_points",
    }
    assert required <= set(report.keys())


def test_build_report_data_history_days_reflects_max_bitmask_length() -> None:
    """Derive history_days from the highest bit_length across all categories."""
    insights = {
        "applications": {"App": {"m": (1 << 20) - 1}},   # bit_length=20
        "providers":    {"P1":  {"m": (1 << 30) - 1}},   # bit_length=30
        "countries":    {},
        "ports":        {"443": {"m": (1 << 15) - 1}},   # bit_length=15
    }
    report = build_report_data(insights)
    assert report["history_days"] == 30


def test_build_report_data_application_total_matches_sum_of_counts() -> None:
    """Verify application_total equals the sum of all recurrence bucket counts."""
    insights = {
        "applications": {
            "App1": {"m": (1 << 25) - 1},   # Stable
            "App2": {"m": 1},               # Seen once
        },
        "countries": {},
    }
    report = build_report_data(insights)
    counts = report["application_counts"]
    assert report["application_total"] == sum(counts.values())
    assert report["application_total"] == 2
