"""Unmapped view rendering for the TapMap UI.

Build the Unmapped modal content from accumulated UnmappedState: PUBLIC
services observed without usable GeoIP coordinates.
"""

from __future__ import annotations

from typing import Any

from dash import html

from .formatting import (
    PENDING_VERIFICATION_STATUS,
    display_verification_status,
    safe_str,
    verification_status_priority,
)
from .tables import ColumnSpec, build_table, cell

_TECHNICAL_COLUMNS = [
    ColumnSpec("Scope", "8%"),
    ColumnSpec("Remote IP", "28%"),
    ColumnSpec("Port", "8%"),
    ColumnSpec("Port service", "20%"),
    ColumnSpec("PID", "12%"),
    ColumnSpec("Process", "24%"),
]

_GENERAL_COLUMNS = [
    ColumnSpec("Application", "34%"),
    ColumnSpec("Creator", "34%"),
    ColumnSpec("Verification", "16%"),
    ColumnSpec("Services", "16%"),
]


def render_unmapped(cache: dict[str, Any], *, technical_details_enabled: bool) -> list[Any]:
    """Build modal content for the Unmapped view from accumulated UnmappedState.

    Args:
        cache: UnmappedState.cache - PUBLIC services observed without usable
            GeoIP coordinates.
        technical_details_enabled: When True, render the per-service
            technical table. When False, render the application-oriented
            summary.
    """
    header = html.H1("Unmapped public services (missing geolocation)", className="mx-h1")

    if not cache:
        return [header, html.Pre("(no unmapped public services)")]

    if technical_details_enabled:
        table = build_table(
            class_name="mx-table mx-unmapped",
            columns=_TECHNICAL_COLUMNS,
            header_cells=[c.header for c in _TECHNICAL_COLUMNS],
            body_rows=_build_technical_rows(cache),
        )
    else:
        table = build_table(
            class_name="mx-table mx-unmapped",
            columns=_GENERAL_COLUMNS,
            header_cells=[c.header for c in _GENERAL_COLUMNS],
            body_rows=_build_general_rows(cache),
        )

    return [header, table]


def _entry_sort_key(item: tuple[str, dict[str, Any]]) -> tuple[str, int]:
    """Return an (ip, port) sort key from a (service_key, entry) pair."""
    _, entry = item
    ip = safe_str(entry.get("ip"))
    port = entry.get("port")
    return (ip, port if isinstance(port, int) else -1)


def _unique_processes(app: dict[str, Any]) -> list[str]:
    """Return sorted distinct process names recorded for one application."""
    processes = app.get("processes")
    if not isinstance(processes, list):
        return []
    return sorted({p.strip() for p in processes if isinstance(p, str) and p.strip()}, key=str.lower)


def _unique_pids(app: dict[str, Any]) -> list[int]:
    """Return sorted distinct PIDs recorded for one application."""
    proc_pids = app.get("proc_pids")
    pids: set[int] = set()
    if isinstance(proc_pids, dict):
        for pid_list in proc_pids.values():
            if isinstance(pid_list, list):
                pids.update(p for p in pid_list if isinstance(p, int) and p > 0)
    return sorted(pids)


def _build_technical_rows(cache: dict[str, Any]) -> list[Any]:
    """Build one technical row per (service, application) pair.

    A row's PID/Process cells summarize every distinct PID and process name
    accumulated for that application at that service - no separate "Count"
    column, since a raw poll-observation count has no honest equivalent once
    the source is accumulated state rather than a single snapshot.
    """
    rows: list[Any] = []

    for _key, entry in sorted(cache.items(), key=_entry_sort_key):
        if not isinstance(entry, dict):
            continue

        applications = entry.get("applications")
        apps = applications if isinstance(applications, dict) else {}

        ip = safe_str(entry.get("ip")) or "-"
        port = entry.get("port")
        port_text = str(port) if isinstance(port, int) and port > 0 else "-"
        service = safe_str(entry.get("service")) or "Unknown"

        for _exe_key, app in sorted(
            apps.items(), key=lambda kv: (safe_str(kv[1].get("app_name")).lower(), kv[0])
        ):
            if not isinstance(app, dict):
                continue

            processes = _unique_processes(app)
            pids = _unique_pids(app)

            rows.append(
                html.Tr(
                    [
                        cell("PUBLIC"),
                        cell(ip),
                        cell(port_text),
                        cell(service),
                        cell(", ".join(str(p) for p in pids)),
                        cell(", ".join(processes) or "-"),
                    ]
                )
            )

    return rows


def _status_text(status: str | None) -> str:
    """Return the display label for a verification status."""
    return {
        "verified": "Verified",
        "failed": "Failed",
        "unknown": "Unknown",
        PENDING_VERIFICATION_STATUS: "Pending",
    }.get(status, "Unknown")


def _build_general_rows(cache: dict[str, Any]) -> list[Any]:
    """Build one row per distinct application, grouped across all unmapped services."""
    groups: dict[str | None, dict[str, Any]] = {}

    for service_key, entry in cache.items():
        if not isinstance(entry, dict):
            continue

        applications = entry.get("applications")
        apps = applications if isinstance(applications, dict) else {}

        for app in apps.values():
            if not isinstance(app, dict):
                continue

            name = app.get("app_name")
            group_key = name if isinstance(name, str) and name.strip() else None

            group = groups.setdefault(
                group_key, {"services": set(), "creator": None, "status": None}
            )
            group["services"].add(service_key)

            creator = app.get("app_creator")
            if not group["creator"] and creator:
                group["creator"] = creator

            status = display_verification_status(app)
            current = group["status"]
            if current is None or verification_status_priority(
                status
            ) < verification_status_priority(current):
                group["status"] = status

    rows: list[Any] = []
    for name, group in sorted(groups.items(), key=lambda kv: (kv[0] or "Unknown").lower()):
        status = group["status"]
        display_name = name or "Unknown"
        creator = (
            "Retrieving..."
            if status == PENDING_VERIFICATION_STATUS
            else (group["creator"] or "Unknown creator")
        )

        rows.append(
            html.Tr(
                [
                    cell(display_name),
                    cell(creator),
                    cell(_status_text(status)),
                    cell(str(len(group["services"]))),
                ]
            )
        )

    return rows
