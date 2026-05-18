"""Insights log writer for TapMap.

Writes a fixed-width ASCII companion log alongside insights.json.
No ANSI escape codes.
"""

from __future__ import annotations

import datetime
import math
import socket
from pathlib import Path
from typing import Any

import pycountry

from tapmap.state.daily_report import (
    HISTORY_WINDOW_DAYS,
    OCCASIONAL_RATIO,
    STABLE_RATIO,
    classify_recurrence,
    get_max_history_days,
)

WIDTH = 86
MAX_LABEL_WIDTH = 36
BOX_FILLED = "\u25a0"
BOX_EMPTY = "\u25a1"


def _country_label(code: str) -> str:
    country = pycountry.countries.get(alpha_2=code)
    if country:
        return f"{country.name} ({code})"
    return code


def _port_service_name(port: str) -> str | None:
    if int(port) >= 1024:
        return None
    for proto in ("tcp", "udp"):
        try:
            name = socket.getservbyport(int(port), proto)
            if name:
                return name.upper()
        except OSError:
            pass
    return None


def _timeline(bitmask: int) -> str:
    """Return a 30-character timeline string, oldest on the left."""
    bits = [
        BOX_FILLED if (bitmask >> i) & 1 else BOX_EMPTY
        for i in range(HISTORY_WINDOW_DAYS - 1, -1, -1)
    ]
    return "[" + "".join(bits) + "]"


def _active_days(bitmask: int) -> int:
    return bitmask.bit_count()


def _entry_line(label: str, bitmask: int) -> str:
    if len(label) > MAX_LABEL_WIDTH:
        label = label[: MAX_LABEL_WIDTH - 1] + "\u2026"
    days = _active_days(bitmask)
    timeline = _timeline(bitmask)
    day_count = f"{days:>2}/{HISTORY_WINDOW_DAYS} days"
    padded_label = f"- {label:<{MAX_LABEL_WIDTH}}"
    return f"{padded_label}  {timeline}  {day_count}"


def _divider(char: str = "-") -> str:
    return char * WIDTH


def _header(title: str, char: str = "=") -> str:
    return f"{char * WIDTH}\n  {title}\n{char * WIDTH}"


def _section_header(title: str) -> str:
    return f"{_divider()}\n  {title}\n{_divider()}"


def _coverage_boundary(sorted_days: list[int], threshold: float) -> int:
    total = sum(sorted_days)
    if total == 0:
        return 0
    target = total * threshold
    cumulative = 0
    for i, d in enumerate(sorted_days, start=1):
        cumulative += d
        if cumulative >= target:
            return i
    return len(sorted_days)


def _build_applications_section(
    state: dict[str, dict[str, Any]],
    history_days: int,
) -> list[str]:
    lines: list[str] = []
    categories = ["Stable", "Recurring", "Occasional", "Seen once"]
    grouped: dict[str, list[tuple[str, int]]] = {c: [] for c in categories}

    for name, item in state.items():
        bitmask = item.get("m")
        if not isinstance(bitmask, int) or bitmask.bit_count() == 0:
            continue
        cat = classify_recurrence(bitmask.bit_count(), history_days)
        grouped[cat].append((name, bitmask))

    for cat in categories:
        grouped[cat].sort(key=lambda x: (-_active_days(x[1]), x[0]))

    stable_min = math.ceil(STABLE_RATIO * history_days)
    recurring_min = math.ceil(OCCASIONAL_RATIO * history_days)
    category_labels = {
        "Stable": f"Stable ({stable_min}-{history_days} days)",
        "Recurring": f"Recurring ({recurring_min}-{stable_min - 1} days)",
        "Occasional": f"Occasional (2-{recurring_min - 1} days)",
        "Seen once": "Seen once (1 day)",
    }

    for cat in categories:
        entries = grouped[cat]
        if not entries:
            continue
        lines.append(f"  {category_labels[cat]}")
        lines.append("")
        for name, bitmask in entries:
            lines.append("  " + _entry_line(name, bitmask))
        lines.append("")

    if lines and lines[-1] == "":
        lines.pop()

    return lines


def _build_providers_section(state: dict[str, dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    entries: list[tuple[str, int]] = []

    for name, item in state.items():
        bitmask = item.get("m")
        if not isinstance(bitmask, int) or bitmask.bit_count() == 0:
            continue
        entries.append((name, bitmask))

    entries.sort(key=lambda x: (-_active_days(x[1]), x[0]))
    sorted_days = [_active_days(bitmask) for _, bitmask in entries]
    top_50 = _coverage_boundary(sorted_days, 0.50)
    top_80 = _coverage_boundary(sorted_days, 0.80)

    one_day_tail: list[tuple[str, int]] = []
    for i, (name, bitmask) in enumerate(entries):
        rank = i + 1
        active = _active_days(bitmask)
        if active == 1 and rank > top_80:
            one_day_tail.append((name, bitmask))
            continue
        lines.append("  " + _entry_line(name, bitmask))
        if rank == top_50:
            lines.append("")
            lines.append(
                f"  -- 50% of activity covered by top {top_50} of {len(entries)} providers"
            )
            lines.append("")
        if rank == top_80 and top_80 != top_50:
            lines.append("")
            lines.append(
                f"  -- 80% of activity covered by top {top_80} of {len(entries)} providers"
            )
            lines.append("")

    if one_day_tail:
        lines.append("")
        lines.append(f"  -- One-day providers ({len(one_day_tail)} entries)")
        lines.append("")
        for name, bitmask in one_day_tail:
            lines.append("  " + _entry_line(name, bitmask))

    lines.append("")
    lines.append(
        f"  Coverage:  50% -> top {top_50}   |   80% -> top {top_80}   |   100% -> {len(entries)}"
    )
    return lines


def _build_countries_section(state: dict[str, dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    entries: list[tuple[str, int]] = []

    for code, item in state.items():
        bitmask = item.get("m")
        if not isinstance(bitmask, int) or bitmask.bit_count() == 0:
            continue
        entries.append((code, bitmask))

    entries.sort(key=lambda x: (-_active_days(x[1]), x[0]))
    labels = {code: _country_label(code) for code, _ in entries}
    sorted_days = [_active_days(bitmask) for _, bitmask in entries]
    top_50 = _coverage_boundary(sorted_days, 0.50)
    top_80 = _coverage_boundary(sorted_days, 0.80)

    for i, (code, bitmask) in enumerate(entries):
        rank = i + 1
        lines.append("  " + _entry_line(labels[code], bitmask))
        if rank == top_50:
            lines.append("")
            lines.append(
                f"  -- 50% of activity covered by top {top_50} of {len(entries)} countries"
            )
            lines.append("")
        if rank == top_80 and top_80 != top_50:
            lines.append("")
            lines.append(
                f"  -- 80% of activity covered by top {top_80} of {len(entries)} countries"
            )
            lines.append("")

    lines.append("")
    lines.append(
        f"  Coverage:  50% -> top {top_50}   |   80% -> top {top_80}   |   100% -> {len(entries)}"
    )
    return lines


def _build_ports_section(state: dict[str, dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    entries: list[tuple[str, int]] = []

    for port, item in state.items():
        bitmask = item.get("m")
        if not isinstance(bitmask, int) or bitmask.bit_count() == 0:
            continue
        entries.append((port, bitmask))

    entries.sort(key=lambda x: (-_active_days(x[1]), int(x[0])))

    def _port_label(port: str) -> str:
        name = _port_service_name(port)
        return f"{port} ({name})" if name else port

    for port, bitmask in entries:
        lines.append("  " + _entry_line(_port_label(port), bitmask))

    return lines


def write_insights_log(
    insights: dict[str, Any],
    log_path: Path,
) -> Path:
    """Write a plain-text insights log to log_path and return the path."""
    history_days = min(get_max_history_days(insights), HISTORY_WINDOW_DAYS)
    generated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    lines: list[str] = []
    lines.append(_header("TAPMAP INSIGHTS LOG"))
    lines.append("")
    lines.append(f"  Generated : {generated_at}")
    lines.append(f"  Window    : {HISTORY_WINDOW_DAYS} days shown  ({history_days} days with data)")
    lines.append("")
    lines.append(
        f"  Legend : {BOX_FILLED} Active day   {BOX_EMPTY} No activity   "
        "Timeline: oldest left, today right"
    )
    lines.append("")

    app_entries = insights.get("applications", {})
    lines.append(_section_header(f"1. APPLICATIONS  ({len(app_entries)})"))
    lines.append("")
    lines.extend(_build_applications_section(app_entries, history_days))
    lines.append("")

    country_entries = insights.get("countries", {})
    lines.append(_section_header(f"2. COUNTRIES  ({len(country_entries)})"))
    lines.append("")
    lines.extend(_build_countries_section(country_entries))
    lines.append("")

    port_entries = insights.get("ports", {})
    lines.append(_section_header(f"3. PORTS  ({len(port_entries)})"))
    lines.append("")
    lines.extend(_build_ports_section(port_entries))
    lines.append("")

    prov_entries = insights.get("providers", {})
    lines.append(_section_header(f"4. PROVIDERS  ({len(prov_entries)})"))
    lines.append("")
    lines.extend(_build_providers_section(prov_entries))
    lines.append("")

    lines.append(_divider("="))
    lines.append("  End of TapMap Insights Log")
    lines.append(_divider("="))
    lines.append("")

    log_path.write_text("\n".join(lines), encoding="utf-8")
    return log_path
