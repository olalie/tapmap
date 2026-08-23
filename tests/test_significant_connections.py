"""Tests for SignificantConnections' bounded, chronological history."""

from __future__ import annotations

import pytest

from tapmap.state.significant_connections import MAX_ENTRIES, SignificantConnections


def _events(n: int) -> list[dict[str, int]]:
    return [{"seq": i} for i in range(n)]


@pytest.mark.parametrize(
    ("count",),
    [(0,), (1,), (MAX_ENTRIES,), (MAX_ENTRIES + 1,), (MAX_ENTRIES + 250,)],
)
def test_construction_trims_to_newest_max_entries(count: int) -> None:
    """__init__ trims to the newest MAX_ENTRIES items, trusting the input's chronological order."""
    items = _events(count)

    history = SignificantConnections(items)

    expected = items[-MAX_ENTRIES:]
    assert history.items == expected
    assert len(history.items) <= MAX_ENTRIES


def test_add_appends_as_newest_and_evicts_oldest_when_over_limit() -> None:
    """add() appends to the end; once over MAX_ENTRIES, the oldest entries are evicted."""
    history = SignificantConnections(_events(MAX_ENTRIES))

    history.add({"seq": "new"})

    assert len(history.items) == MAX_ENTRIES
    assert history.items[-1] == {"seq": "new"}
    assert history.items[0] == {"seq": 1}


def test_add_below_limit_does_not_evict() -> None:
    """add() below the limit simply appends without dropping anything."""
    history = SignificantConnections(_events(3))

    history.add({"seq": "new"})

    assert history.items == [{"seq": 0}, {"seq": 1}, {"seq": 2}, {"seq": "new"}]
