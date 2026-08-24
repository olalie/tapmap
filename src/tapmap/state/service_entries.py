"""Shared per-service entry identity and application/process bookkeeping.

Used by both ConnectionState (mapped) and UnmappedState (unmapped). Every
function here operates purely on the {exe_or_UNKNOWN_APP_KEY: {app_*, exe,
processes, proc_pids}} "applications" sub-dict convention, with no
dependency on which kind of service entry it is attached to.
"""

from __future__ import annotations

from typing import Any

UNKNOWN_APP_KEY = "__unknown_application__"


def service_key(ip: str, port: int) -> str:
    """Return the identity key for a service entry."""
    return f"{ip}|{port}"


def new_application(exe: str | None) -> dict[str, Any]:
    """Return a new, empty application record for one executable path."""
    return {
        "app_name": None,
        "app_creator": None,
        "app_verification_status": None,
        "app_signature_state": None,
        "app_signature_state_details": None,
        "exe": exe,
        "processes": [],
        "proc_pids": {},
    }


def merge_missing_attrs(
    entry: dict[str, Any],
    candidate: dict[str, Any],
    *,
    attrs: tuple[str, ...],
) -> None:
    """Fill attrs on entry from candidate, but only where entry's value is still None."""
    for attr in attrs:
        if entry.get(attr) is None and candidate.get(attr) is not None:
            entry[attr] = candidate.get(attr)


def merge_application(
    entry: dict[str, Any],
    *,
    exe: str | None,
    candidate: dict[str, Any],
    process_name: str,
    pid: int | None,
) -> None:
    """Merge one candidate's application metadata into its exe-keyed bucket.

    Candidates with no resolvable exe path share UNKNOWN_APP_KEY, since
    no reliable identity exists to key them individually.
    """
    applications = entry.get("applications")
    apps: dict[str, Any] = applications if isinstance(applications, dict) else {}
    entry["applications"] = apps

    app_key = exe or UNKNOWN_APP_KEY
    app = apps.get(app_key)
    if not isinstance(app, dict):
        app = new_application(exe)
        apps[app_key] = app

    merge_missing_attrs(
        app,
        candidate,
        attrs=(
            "app_name",
            "app_creator",
            "app_verification_status",
            "app_signature_state",
            "app_signature_state_details",
        ),
    )

    if process_name:
        merge_process(app, process_name=process_name, pid=pid)


def merge_process(record: dict[str, Any], *, process_name: str, pid: int | None) -> None:
    """Accumulate one process name and its PID into an application record."""
    processes = record.get("processes")
    proc_list = processes if isinstance(processes, list) else []
    proc_set = {p.strip() for p in proc_list if isinstance(p, str) and p.strip()}
    proc_set.add(process_name)
    record["processes"] = sorted(proc_set, key=str.lower)

    proc_pids = record.get("proc_pids")
    proc_pids_map: dict[str, list[int]] = proc_pids if isinstance(proc_pids, dict) else {}
    record["proc_pids"] = proc_pids_map

    if pid is None:
        return

    existing = proc_pids_map.get(process_name)
    existing_list = existing if isinstance(existing, list) else []
    pid_set = {int(x) for x in existing_list if isinstance(x, int) and x > 0}
    pid_set.add(pid)
    proc_pids_map[process_name] = sorted(pid_set)


def pending_exe_paths(cache: dict[str, Any]) -> set[str]:
    """Return exe paths in cache whose deferred AppInfo data is still missing.

    Scans the accumulated cache, not the current snapshot, so retained
    applications whose connection has vanished are still included.
    Excludes the synthetic unknown-application bucket and applications
    already resolved.
    """
    pending: set[str] = set()
    for entry in cache.values():
        if not isinstance(entry, dict):
            continue
        applications = entry.get("applications")
        if not isinstance(applications, dict):
            continue
        for app in applications.values():
            if not isinstance(app, dict):
                continue
            exe = app.get("exe")
            if not isinstance(exe, str) or not exe:
                continue
            if app.get("app_verification_status") is None:
                pending.add(exe)
    return pending


def refresh_resolved_applications(
    cache: dict[str, Any], resolved: dict[str, dict[str, Any]]
) -> None:
    """Backfill newly-completed AppInfo fields into matching application records.

    resolved maps exe path to a plain dict of app_creator,
    app_verification_status, app_signature_state, and
    app_signature_state_details values. Only fills fields still None, so
    calling this every poll tick is safe even when nothing changed.
    Mutates cache in place.
    """
    if not resolved:
        return
    for entry in cache.values():
        if not isinstance(entry, dict):
            continue
        applications = entry.get("applications")
        if not isinstance(applications, dict):
            continue
        for app in applications.values():
            if not isinstance(app, dict):
                continue
            exe = app.get("exe")
            if not isinstance(exe, str):
                continue
            update = resolved.get(exe)
            if update is None:
                continue
            merge_missing_attrs(
                app,
                update,
                attrs=(
                    "app_creator",
                    "app_verification_status",
                    "app_signature_state",
                    "app_signature_state_details",
                ),
            )
