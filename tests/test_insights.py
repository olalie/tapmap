"""Regression tests for the rolling 30-day bitmap semantics in process_insights."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from unittest.mock import patch

import pytest

from tapmap.state.insights import process_insights

# Fixed base ordinal: avoids any dependency on the wall clock.
_BASE = date(2000, 1, 1).toordinal()


def _day(n: int) -> int:
    """Return the ordinal for test day n (1-based; n=1 maps to _BASE)."""
    return _BASE + n - 1


def _now(n: int) -> datetime:
    """Return a deterministic datetime whose ordinal equals _day(n)."""
    d = date.fromordinal(_day(n))
    return datetime(d.year, d.month, d.day, 12, 0, 0)


def _snap(*country_codes: str) -> list[dict[str, Any]]:
    """Build a minimal PUBLIC snapshot for the given country codes."""
    return [{"service_scope": "PUBLIC", "country_code": cc} for cc in country_codes]


def _call(
    state: dict[str, Any],
    values: list[str],
    day_n: int,
) -> dict[str, Any]:
    """Drive process_insights against the countries dimension; return the mutated state."""
    insights: dict[str, Any] = {
        "countries": state,
        "providers": {},
        "ports": {},
        "applications": {},
    }
    process_insights(_snap(*values), insights, _now(day_n))
    return insights["countries"]


def _bits(*offsets: int) -> int:
    """Return a bitmask with the given bit positions set (position 0 = today's bit)."""
    return sum(1 << i for i in offsets)


def _output_new(
    state: dict[str, Any],
    values: list[str],
    day_n: int,
) -> list[dict[str, Any]]:
    """Call process_insights and return the new['countries'] output list."""
    insights: dict[str, Any] = {
        "countries": state,
        "providers": {},
        "ports": {},
        "applications": {},
    }
    result = process_insights(_snap(*values), insights, _now(day_n))
    return result["new"]["countries"]


def _output_top(
    state: dict[str, Any],
    day_n: int,
) -> list[dict[str, Any]]:
    """Return top['countries'] from a call with no snapshot items."""
    insights: dict[str, Any] = {
        "countries": state,
        "providers": {},
        "ports": {},
        "applications": {},
    }
    result = process_insights([], insights, _now(day_n))
    return result["top"]["countries"]


class TestBitmaskEvolution:
    """Bitmask bit positions are correct after observation gaps."""

    def test_first_observation_sets_bit_0(self) -> None:
        """New entry on day 1: m=1 (bit 0 only)."""
        state: dict[str, Any] = {}
        state = _call(state, ["US"], 1)
        assert state["US"]["m"] == _bits(0)

    def test_first_observation_sets_anchor_to_today(self) -> None:
        """New entry on day 1: l == ordinal of day 1."""
        state: dict[str, Any] = {}
        state = _call(state, ["US"], 1)
        assert state["US"]["l"] == _day(1)

    @pytest.mark.parametrize("obs_day, call_day, expected_m", [
        (1, 1,  _bits(0)),           # same day: idempotent
        (1, 2,  _bits(0, 1)),        # consecutive days
        (1, 5,  _bits(0, 4)),        # 4-day gap
        (1, 15, _bits(0, 14)),       # 14-day gap
        (1, 30, _bits(0, 29)),       # 29-day gap: last bit still in window (M1)
    ])
    def test_bit_positions_after_gap(
        self,
        obs_day: int,
        call_day: int,
        expected_m: int,
    ) -> None:
        """Expected bits set after observation gap."""
        state: dict[str, Any] = {}
        state = _call(state, ["US"], obs_day)
        state = _call(state, ["US"], call_day)
        assert state["US"]["m"] == expected_m

    def test_30_consecutive_days_saturates_all_bits(self) -> None:
        """Thirty consecutive days of activity sets all 30 bits."""
        state: dict[str, Any] = {}
        for n in range(1, 31):
            state = _call(state, ["US"], n)
        assert state["US"]["m"] == (1 << 30) - 1

    def test_alternating_days_sets_alternating_bits(self) -> None:
        """Observed on days 1, 3, 5 (relative to day 5): bits 0, 2, 4."""
        state: dict[str, Any] = {}
        state = _call(state, ["US"], 1)
        state = _call(state, ["US"], 3)
        state = _call(state, ["US"], 5)
        assert state["US"]["m"] == _bits(0, 2, 4)


class TestDeltaBoundaries:
    """Exact delta=29/30/31 behaviour and mask-width edge cases."""

    # M1: delta=29 is the last day inside the window.
    def test_m1_delta_29_not_observed_entry_survives_with_bit_29(self) -> None:
        """M1: delta=29 without re-observation → survives with bit 29."""
        state: dict[str, Any] = {}
        state = _call(state, ["US"], 1)
        state = _call(state, [], 30)
        assert "US" in state
        assert state["US"]["m"] == _bits(29)

    # M2: delta=30 zeros m → entry pruned when not re-observed.
    def test_m2_delta_30_not_observed_entry_is_pruned(self) -> None:
        """M2: delta=30 without re-observation → pruned."""
        state: dict[str, Any] = {}
        state = _call(state, ["US"], 1)
        state = _call(state, [], 31)
        assert "US" not in state

    # M3: delta=30, re-observed → m=1, treated as new.
    def test_m3_delta_30_reobserved_yields_m_equals_1(self) -> None:
        """M3: delta=30 with re-observation → m=1; prior activity lost."""
        state: dict[str, Any] = {}
        state = _call(state, ["US"], 1)
        state = _call(state, ["US"], 31)
        assert state["US"]["m"] == 1

    # M4: delta=29, re-observed → two bits set, NOT new.
    def test_m4_delta_29_reobserved_has_two_bits_and_is_not_new(self) -> None:
        """M4: delta=29 with re-observation → bits 0 and 29 set; m != 1."""
        state: dict[str, Any] = {}
        state = _call(state, ["US"], 1)
        state = _call(state, ["US"], 30)
        assert state["US"]["m"] == _bits(0, 29)
        assert state["US"]["m"] != 1

    # M5: bit 29 + delta=1 shifts out of the 30-bit mask.
    def test_m5_bit_29_aged_one_day_shifts_out_of_mask(self) -> None:
        """M5: entry with only bit 29, aged by 1 day → shifts past mask → pruned."""
        state: dict[str, Any] = {"US": {"l": _day(1), "m": _bits(29)}}
        state = _call(state, [], 2)
        assert "US" not in state

    # M6: same-day, disjoint snapshots → both entries have bit 0.
    def test_m6_disjoint_snapshots_same_day_both_have_bit_0(self) -> None:
        """M6: snapshot {US} then {DE} on same day → US.m=1 and DE.m=1."""
        state: dict[str, Any] = {}
        state = _call(state, ["US"], 1)
        state = _call(state, ["DE"], 1)
        assert state["US"]["m"] == 1
        assert state["DE"]["m"] == 1

    @pytest.mark.parametrize("delta", [30, 31, 50, 100])
    def test_large_delta_not_observed_prunes_entry(self, delta: int) -> None:
        """Any delta >= 30 zeros m; entry is pruned when not re-observed."""
        state: dict[str, Any] = {}
        state = _call(state, ["US"], 1)
        state = _call(state, [], 1 + delta)
        assert "US" not in state

    @pytest.mark.parametrize("delta", [30, 31, 50])
    def test_large_delta_reobserved_yields_m_equals_1(self, delta: int) -> None:
        """Any delta >= 30 followed by re-observation → m=1."""
        state: dict[str, Any] = {}
        state = _call(state, ["US"], 1)
        state = _call(state, ["US"], 1 + delta)
        assert state["US"]["m"] == 1

    def test_delta_28_not_observed_survives(self) -> None:
        """delta=28 leaves one bit inside the window; entry survives."""
        state: dict[str, Any] = {}
        state = _call(state, ["US"], 1)
        state = _call(state, [], 29)
        assert "US" in state
        assert state["US"]["m"] == _bits(28)


class TestAnchorDaySemantics:
    """l is the bitmap anchor day, not the last observation day."""

    def test_anchor_updated_on_aging_even_when_not_observed(self) -> None:
        """Aging without observation advances l to today."""
        state: dict[str, Any] = {}
        state = _call(state, ["US"], 1)
        state = _call(state, [], 5)
        assert "US" in state
        assert state["US"]["l"] == _day(5)

    def test_anchor_unchanged_when_delta_is_zero(self) -> None:
        """delta=0: l unchanged."""
        state: dict[str, Any] = {"US": {"l": _day(5), "m": 0b11}}
        state = _call(state, [], 5)
        assert state["US"]["l"] == _day(5)

    def test_anchor_updated_by_step2_after_stale_aging(self) -> None:
        """Re-observation after delta=30: l == today and m == 1."""
        state: dict[str, Any] = {"US": {"l": _day(1), "m": 1}}
        state = _call(state, ["US"], 31)
        assert state["US"]["l"] == _day(31)

    def test_anchor_equals_today_for_all_surviving_entries_after_call(self) -> None:
        """After any call, every surviving entry has l == today."""
        state: dict[str, Any] = {}
        state = _call(state, ["US", "DE"], 1)
        state = _call(state, ["DE"], 10)
        today = _day(10)
        for entry in state.values():
            assert entry["l"] == today

    def test_anchor_tracks_last_aging_day_across_multiple_steps(self) -> None:
        """Entry aged day 1 → 3 → 7 without observation: l == day(7) and bits preserved."""
        state: dict[str, Any] = {}
        state = _call(state, ["US"], 1)
        state = _call(state, [], 3)
        state = _call(state, [], 7)
        assert state["US"]["l"] == _day(7)
        # Day 1 activity is now 6 days old → bit 6
        assert state["US"]["m"] == _bits(6)


class TestPruning:
    """Entries with m=0 are removed; other entries survive."""

    def test_empty_state_stays_empty(self) -> None:
        """Empty state with empty snapshot remains empty."""
        state = _call({}, [], 1)
        assert state == {}

    def test_stale_entry_not_reobserved_is_removed(self) -> None:
        """delta=30 without re-observation: removed."""
        state: dict[str, Any] = {}
        state = _call(state, ["US"], 1)
        state = _call(state, [], 31)
        assert state == {}

    def test_only_stale_entry_pruned_active_entry_survives(self) -> None:
        """Stale US removed; active DE survives."""
        state: dict[str, Any] = {}
        state = _call(state, ["US", "DE"], 1)
        state = _call(state, ["DE"], 31)
        assert "US" not in state
        assert "DE" in state

    def test_all_entries_pruned_yields_empty_state(self) -> None:
        """All entries stale and absent: state becomes empty."""
        state: dict[str, Any] = {}
        state = _call(state, ["US", "DE", "NO"], 1)
        state = _call(state, [], 35)
        assert state == {}

    def test_entry_reobserved_after_being_pruned_is_fresh(self) -> None:
        """Re-added after pruning: m=1, l == today."""
        state: dict[str, Any] = {}
        state = _call(state, ["US"], 1)
        state = _call(state, [], 31)          # pruned
        state = _call(state, ["US"], 50)      # re-added
        assert state["US"]["m"] == 1
        assert state["US"]["l"] == _day(50)


class TestSameDayAccumulation:
    """Multiple snapshots per calendar day are additive."""

    def test_same_key_two_calls_same_day_is_idempotent(self) -> None:
        """Two calls with the same key on the same day leave m=1."""
        state: dict[str, Any] = {}
        state = _call(state, ["US"], 1)
        state = _call(state, ["US"], 1)
        assert state["US"]["m"] == 1

    def test_bit_0_set_in_first_snapshot_survives_second_snapshot(self) -> None:
        """Bit 0 set by snapshot 1 is not cleared when the key is absent in snapshot 2."""
        state: dict[str, Any] = {}
        state = _call(state, ["US"], 1)
        state = _call(state, [], 1)
        assert state["US"]["m"] == 1

    def test_union_equivalence_for_disjoint_same_day_snapshots(self) -> None:
        """Two calls with {US} then {DE} on same day is equivalent to one call with {US, DE}."""
        state_split: dict[str, Any] = {}
        state_split = _call(state_split, ["US"], 1)
        state_split = _call(state_split, ["DE"], 1)

        state_combined: dict[str, Any] = {}
        state_combined = _call(state_combined, ["US", "DE"], 1)

        assert state_split["US"]["m"] == state_combined["US"]["m"]
        assert state_split["DE"]["m"] == state_combined["DE"]["m"]

    def test_next_day_aging_advances_accumulated_bits(self) -> None:
        """Bits accumulated on day 1 shift correctly to position 1 on day 2."""
        state: dict[str, Any] = {}
        state = _call(state, ["US"], 1)
        state = _call(state, ["US"], 1)  # second snapshot same day
        state = _call(state, ["US"], 2)  # next day
        assert state["US"]["m"] == _bits(0, 1)

    def test_many_same_day_calls_with_distinct_values_all_have_bit_0(self) -> None:
        """Five successive same-day snapshots with one new key each: all have bit 0."""
        codes = ["US", "DE", "NO", "GB", "JP"]
        state: dict[str, Any] = {}
        for cc in codes:
            state = _call(state, [cc], 1)
        for cc in codes:
            assert state[cc]["m"] == 1


class TestBuildNew:
    """build_new: m == 1 is the exact condition for 'new'."""

    def test_first_observation_appears_in_new(self) -> None:
        """Key observed for the first time (m=1) appears in new output."""
        new = _output_new({}, ["US"], 1)
        assert any(x["value"] == "US" for x in new)

    def test_key_with_prior_day_history_is_not_new(self) -> None:
        """Key observed yesterday and today (m=0b11) is not in new."""
        state: dict[str, Any] = {}
        _call(state, ["US"], 1)
        new = _output_new(state, ["US"], 2)
        assert not any(x["value"] == "US" for x in new)

    def test_delta_30_reobservation_is_new(self) -> None:
        """Key re-observed after 30-day gap (m=1 after stale) appears in new."""
        state: dict[str, Any] = {}
        _call(state, ["US"], 1)
        new = _output_new(state, ["US"], 31)
        assert any(x["value"] == "US" for x in new)

    def test_delta_29_reobservation_is_not_new(self) -> None:
        """Key re-observed after 29-day gap (two bits set) does not appear in new."""
        state: dict[str, Any] = {}
        _call(state, ["US"], 1)
        new = _output_new(state, ["US"], 30)
        assert not any(x["value"] == "US" for x in new)

    def test_entry_with_single_old_bit_not_today_is_not_new(self) -> None:
        """Entry active 15 days ago but not today is not in new (m != 1, bit 0 not set)."""
        # Pre-populate with bit 15 set (observed 15 days ago relative to anchor).
        # Call today with US absent → bit 15 shifts, bit 0 not set → not new.
        state: dict[str, Any] = {"US": {"l": _day(1), "m": _bits(14)}}
        # Advance one day without observing US: l → day(2), m shifts to bit 15
        new = _output_new(state, [], 2)
        assert not any(x["value"] == "US" for x in new)

    def test_country_new_entry_has_value_and_name_keys(self) -> None:
        """Country entries in new output include both 'value' and 'name'."""
        new = _output_new({}, ["US"], 1)
        assert len(new) == 1
        assert "value" in new[0]
        assert "name" in new[0]

    def test_unknown_country_code_falls_back_to_code_as_name(self) -> None:
        """An unrecognised country code uses the code itself as the name."""
        with patch("tapmap.state.insights.pycountry") as mock_pc:
            mock_pc.countries.get.return_value = None
            new = _output_new({}, ["XX"], 1)
        assert new[0]["value"] == "XX"
        assert new[0]["name"] == "XX"

    def test_non_country_new_entry_has_value_key_only(self) -> None:
        """Non-country entries in new output have 'value' but not 'name'."""
        items = [{"service_scope": "PUBLIC", "asn_org": "Acme Inc"}]
        insights: dict[str, Any] = {}
        result = process_insights(items, insights, _now(1))
        new_providers = result["new"]["providers"]
        assert len(new_providers) == 1
        assert new_providers[0]["value"] == "Acme Inc"
        assert "name" not in new_providers[0]

    def test_empty_snapshot_produces_no_new_entries(self) -> None:
        """Empty snapshot: no entries appear in new."""
        new = _output_new({}, [], 1)
        assert new == []


class TestBuildTop:
    """build_top: ranks by bit_count with inclusive tie-breaking at the cutoff."""

    def test_higher_bit_count_ranks_first(self) -> None:
        """Entry with more active days ranks above entry with fewer."""
        state = {
            "US": {"l": _day(1), "m": _bits(0, 1, 2)},  # bit_count=3
            "DE": {"l": _day(1), "m": _bits(0)},          # bit_count=1
        }
        top = _output_top(state, 1)
        assert top[0]["value"] == "US"
        assert top[1]["value"] == "DE"

    def test_fewer_than_limit_returns_all(self) -> None:
        """Fewer than 5 entries: all are returned."""
        state = {
            "US": {"l": _day(1), "m": 0b111},
            "DE": {"l": _day(1), "m": 0b11},
        }
        top = _output_top(state, 1)
        assert len(top) == 2

    def test_exactly_limit_entries_returns_all(self) -> None:
        """Exactly 5 distinct entries: all 5 returned."""
        state = {k: {"l": _day(1), "m": 1 << i} for i, k in enumerate(["A","B","C","D","E"])}
        top = _output_top(state, 1)
        assert len(top) == 5

    def test_inclusive_tie_breaking_exceeds_limit(self) -> None:
        """All entries tied at cutoff are included; result count may exceed limit."""
        state = {
            "A": {"l": _day(1), "m": _bits(0, 1, 2, 3)},  # 4
            "B": {"l": _day(1), "m": _bits(0, 1, 2)},     # 3
            "C": {"l": _day(1), "m": _bits(0, 1, 2)},     # 3
            "D": {"l": _day(1), "m": _bits(0, 1)},        # 2
            "E": {"l": _day(1), "m": _bits(0, 1)},        # 2
            "F": {"l": _day(1), "m": _bits(0, 1)},        # 2
            "G": {"l": _day(1), "m": _bits(0)},           # 1
        }
        # Sorted: A=4, B=3, C=3, D=2, E=2, F=2, G=1
        # limit=5, cutoff=items[4][1]=2 → include A,B,C,D,E,F → 6 entries
        top = _output_top(state, 1)
        assert len(top) == 6
        returned = {x["value"] for x in top}
        assert "G" not in returned

    def test_entries_below_cutoff_excluded(self) -> None:
        """Entries with score strictly below cutoff are not returned."""
        state = {
            "A": {"l": _day(1), "m": _bits(0,1,2,3,4)},  # 5
            "B": {"l": _day(1), "m": _bits(0,1,2,3)},    # 4
            "C": {"l": _day(1), "m": _bits(0,1,2)},      # 3
            "D": {"l": _day(1), "m": _bits(0,1)},        # 2
            "E": {"l": _day(1), "m": _bits(0,1)},        # 2
            "F": {"l": _day(1), "m": _bits(0)},          # 1 — below cutoff
        }
        # cutoff = items[4][1] = 2; F has score 1 → excluded
        top = _output_top(state, 1)
        assert not any(x["value"] == "F" for x in top)

    def test_empty_state_returns_empty_top(self) -> None:
        """Empty state produces an empty top list."""
        top = _output_top({}, 1)
        assert top == []

    def test_top_country_entries_have_value_and_name(self) -> None:
        """Top country entries include both 'value' and 'name'."""
        state = {"US": {"l": _day(1), "m": 0b11}}
        top = _output_top(state, 1)
        assert len(top) == 1
        assert "value" in top[0]
        assert "name" in top[0]


class TestInputFiltering:
    """process_insights correctly classifies and filters snapshot items."""

    def test_private_scope_item_is_ignored(self) -> None:
        """Items with service_scope != 'PUBLIC' are not counted in any dimension."""
        items = [{"service_scope": "PRIVATE", "country_code": "US"}]
        insights: dict[str, Any] = {}
        process_insights(items, insights, _now(1))
        assert insights.get("countries", {}) == {}

    def test_none_country_code_is_not_added(self) -> None:
        """country_code=None is skipped."""
        items = [{"service_scope": "PUBLIC", "country_code": None}]
        insights: dict[str, Any] = {}
        process_insights(items, insights, _now(1))
        assert insights.get("countries", {}) == {}

    def test_empty_string_country_code_is_not_added(self) -> None:
        """country_code='' is skipped."""
        items = [{"service_scope": "PUBLIC", "country_code": ""}]
        insights: dict[str, Any] = {}
        process_insights(items, insights, _now(1))
        assert insights.get("countries", {}) == {}

    def test_non_int_port_is_not_added(self) -> None:
        """port as a string is not added to ports."""  # noqa: D403
        items = [{"service_scope": "PUBLIC", "port": "443"}]
        insights: dict[str, Any] = {}
        process_insights(items, insights, _now(1))
        assert insights.get("ports", {}) == {}

    def test_int_port_is_added_as_string_key(self) -> None:
        """port=443 (int) is stored under key '443'."""
        items = [{"service_scope": "PUBLIC", "port": 443}]
        insights: dict[str, Any] = {}
        process_insights(items, insights, _now(1))
        assert "443" in insights.get("ports", {})

    def test_non_dict_items_are_skipped(self) -> None:
        """Non-dict entries in the list are silently ignored; valid items still processed."""
        items: list[Any] = [
            "not a dict",
            42,
            None,
            {"service_scope": "PUBLIC", "country_code": "US"},
        ]
        insights: dict[str, Any] = {}
        process_insights(items, insights, _now(1))
        assert "US" in insights.get("countries", {})

    def test_empty_items_list_does_not_add_entries(self) -> None:
        """Empty snapshot: no new entries; existing state is aged but not extended."""
        state: dict[str, Any] = {"US": {"l": _day(1), "m": 1}}
        insights: dict[str, Any] = {
            "countries": state,
            "providers": {},
            "ports": {},
            "applications": {},
        }
        process_insights([], insights, _now(1))  # same day, delta=0
        assert list(insights["countries"].keys()) == ["US"]
        assert insights["countries"]["US"]["m"] == 1

    def test_all_four_dimensions_populated_from_one_complete_item(self) -> None:
        """A single complete PUBLIC item updates all four dimensions."""
        items = [{
            "service_scope": "PUBLIC",
            "country_code": "US",
            "asn_org": "Acme Inc",
            "port": 443,
            "process_name": "nginx",
        }]
        insights: dict[str, Any] = {}
        process_insights(items, insights, _now(1))
        assert "US" in insights["countries"]
        assert "Acme Inc" in insights["providers"]
        assert "443" in insights["ports"]
        assert "nginx" in insights["applications"]

    def test_missing_service_scope_field_is_not_treated_as_public(self) -> None:
        """Item with no service_scope key is not counted (treated as non-PUBLIC)."""
        items = [{"country_code": "US", "port": 80}]
        insights: dict[str, Any] = {}
        process_insights(items, insights, _now(1))
        assert insights.get("countries", {}) == {}
        assert insights.get("ports", {}) == {}
