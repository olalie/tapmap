"""Unit tests for deterministic helpers in state.insights_log."""

from __future__ import annotations

from tapmap.state.insights_log import (
    BOX_EMPTY,
    BOX_FILLED,
    HISTORY_WINDOW_DAYS,
    MAX_LABEL_WIDTH,
    _coverage_boundary,
    _entry_line,
    _timeline,
)

# --- _timeline ---


def test_timeline_today_only() -> None:
    """Produce a timeline with only today's position filled."""
    # m=1: bit 0 (today) is the only set bit.
    result = _timeline(1)
    expected = "[" + BOX_EMPTY * 29 + BOX_FILLED + "]"
    assert result == expected


def test_timeline_all_30_days_active() -> None:
    """Produce a fully-filled timeline when all 30 bits are set."""
    result = _timeline((1 << 30) - 1)
    expected = "[" + BOX_FILLED * 30 + "]"
    assert result == expected


def test_timeline_specific_bit_positions() -> None:
    """Reflect the exact bitmask pattern in character positions."""
    # m=0b101: bits 0 and 2 set → positions 27 and 29 filled (oldest-left layout)
    result = _timeline(0b101)
    chars = result[1:-1]   # strip surrounding brackets
    assert len(chars) == HISTORY_WINDOW_DAYS
    # Positions 0..26 (indices for bits 29..3): all empty
    assert all(c == BOX_EMPTY for c in chars[:27])
    # Position 27 (bit 2): filled
    assert chars[27] == BOX_FILLED
    # Position 28 (bit 1): empty
    assert chars[28] == BOX_EMPTY
    # Position 29 (bit 0, today): filled
    assert chars[29] == BOX_FILLED


# --- _entry_line ---


def test_entry_line_short_label_not_truncated() -> None:
    """Include the full label when it fits within MAX_LABEL_WIDTH."""
    label = "Firefox"
    result = _entry_line(label, 1)
    assert label in result
    assert "\u2026" not in result


def test_entry_line_label_at_exact_max_width_not_truncated() -> None:
    """Do not truncate a label that is exactly MAX_LABEL_WIDTH characters."""
    label = "A" * MAX_LABEL_WIDTH
    result = _entry_line(label, 1)
    assert label in result
    assert "\u2026" not in result


def test_entry_line_long_label_truncated_with_ellipsis() -> None:
    """Truncate labels longer than MAX_LABEL_WIDTH and append an ellipsis."""
    label = "A" * (MAX_LABEL_WIDTH + 4)
    result = _entry_line(label, 1)
    assert "\u2026" in result
    assert label not in result


def test_entry_line_day_count_format() -> None:
    """Show active_days/HISTORY_WINDOW_DAYS in the entry line."""
    # 30 active days: bit_count of (1<<30)-1 = 30
    result = _entry_line("App", (1 << 30) - 1)
    assert "30/30 days" in result


def test_entry_line_single_day_count_right_aligned() -> None:
    """Right-align single-digit active day count."""
    # m=1: bit_count=1
    result = _entry_line("App", 1)
    assert " 1/30 days" in result


# --- _coverage_boundary ---


def test_coverage_boundary_empty_list_returns_zero() -> None:
    """Return 0 for an empty input list."""
    assert _coverage_boundary([], 0.5) == 0


def test_coverage_boundary_single_element_always_covers_threshold() -> None:
    """Return 1 when a single element covers the threshold."""
    assert _coverage_boundary([10], 0.5) == 1
    assert _coverage_boundary([10], 0.99) == 1


def test_coverage_boundary_50_percent_threshold() -> None:
    """Return the index where cumulative sum first meets 50% of the total."""
    # Total=10, target=5; after element 1: 3<5; after element 2: 5>=5 → 2
    assert _coverage_boundary([3, 2, 2, 1, 1, 1], 0.5) == 2


def test_coverage_boundary_80_percent_threshold() -> None:
    """Return the correct index for an 80% threshold."""
    # Total=20, target=16; after 1: 10<16; after 2: 15<16; after 3: 20>=16 → 3
    assert _coverage_boundary([10, 5, 5], 0.8) == 3


def test_coverage_boundary_threshold_met_at_first_element() -> None:
    """Return 1 when the first element already meets the threshold."""
    # Total=10, target=5; after element 1: 5>=5 → 1
    assert _coverage_boundary([5, 5], 0.5) == 1


def test_coverage_boundary_all_equal_elements() -> None:
    """Return the correct midpoint for uniformly distributed activity."""
    # 4 equal elements, threshold=0.5: need 2 of 4 → index 2
    assert _coverage_boundary([10, 10, 10, 10], 0.5) == 2
