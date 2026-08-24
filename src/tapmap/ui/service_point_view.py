"""Service point view preparation helpers for the TapMap UI.

Build map points, hover summaries, and click details from the
accumulated per-service cache owned by ConnectionState.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from ..state.connection_state import UNKNOWN_APP_KEY
from .formatting import (
    PENDING_VERIFICATION_STATUS,
    country_flag,
    elide_path_middle,
    humanize_camel_case,
    safe_str,
    verification_status_color,
    verification_status_glyph,
)

_APP_VERIFICATION_STATUS_PRIORITY: dict[str | None, int] = {
    "failed": 0,
    "unknown": 1,
    PENDING_VERIFICATION_STATUS: 2,
    "verified": 3,
}


class ServicePointViewBuilder:
    """Build map view data grouped into ServicePoints."""

    _UNKNOWN_APP_KEY = UNKNOWN_APP_KEY

    def __init__(
        self,
        coord_precision: int = 3,
        is_docker: bool = False,
    ) -> None:
        self.coord_precision = int(coord_precision)
        self.is_docker = bool(is_docker)

    @staticmethod
    def _fmt_ip_port(ip: str, port: int) -> str:
        ip_text = ip or "?"
        port_text = str(port) if port > 0 else "-"
        if ":" in ip_text and not ip_text.startswith("["):
            return f"[{ip_text}]:{port_text}"
        return f"{ip_text}:{port_text}"

    @staticmethod
    def _safe_proto(value: Any) -> str:
        p = str(value).strip().lower() if value else "tcp"
        return p if p in {"tcp", "udp"} else "tcp"

    @staticmethod
    def format_list_compact(items: list[Any], max_items: int) -> str:
        """Format items as comma-separated values with optional +N overflow."""
        cleaned: list[str] = []
        for item in items:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                cleaned.append(text)

        if not cleaned:
            return "-"

        if len(cleaned) <= max_items:
            return ", ".join(cleaned)

        shown = ", ".join(cleaned[:max_items])
        return f"{shown} +{len(cleaned) - max_items}"

    def build_view_from_cache(
        self, cache: dict[str, Any], technical_details_enabled: bool
    ) -> dict[str, Any]:
        """Group cached entries by rounded coordinates and build map view data.

        Args:
            cache: Per-service cache from ConnectionState.merge/clear.
            technical_details_enabled: When True, hover summaries use the
                connection-oriented format. When False, hover summaries use
                the application-oriented format. Click details are
                unaffected either way.
        """
        groups = self._group_by_coord(cache if isinstance(cache, dict) else {})

        points: list[tuple[float, float]] = []
        summaries: dict[str, str] = {}
        details: dict[str, str] = {}
        point_ips: dict[str, list[str]] = {}

        for idx, coord in enumerate(sorted(groups)):
            entries = groups[coord]
            lon, lat = coord
            points.append((lon, lat))

            ips = {
                e["ip"]
                for e in entries
                if isinstance(e, dict) and isinstance(e.get("ip"), str)
            }
            point_ips[idx] = list(ips)

            place = self._pick_place(entries)
            unique_orgs = self._unique_network_orgs(entries)
            service_count = len(entries)

            key_str = str(idx)
            if technical_details_enabled:
                summaries[key_str] = self._build_hover_summary(
                    place=place,
                    service_count=service_count,
                    entries=entries,
                    unique_orgs=unique_orgs,
                )
                details[key_str] = self._build_click_details(
                    lon=lon,
                    lat=lat,
                    place=place,
                    entries=entries,
                    unique_orgs=unique_orgs,
                )
            else:
                country_code = self._pick_country_code(entries)
                summaries[key_str] = self._build_app_summary(
                    place=place,
                    country_code=country_code,
                    entries=entries,
                )
                details[key_str] = self._build_app_click_details(
                    place=place,
                    country_code=country_code,
                    entries=entries,
                )

        return {
            "points": points,
            "summaries": summaries,
            "details": details,
            "point_ips": point_ips,
        }

    def _group_by_coord(
        self, cache: dict[str, Any]
    ) -> dict[tuple[float, float], list[dict[str, Any]]]:
        groups: dict[tuple[float, float], list[dict[str, Any]]] = defaultdict(list)

        for raw in cache.values():
            if not isinstance(raw, dict):
                continue

            lon = raw.get("lon")
            lat = raw.get("lat")
            if lon is None or lat is None:
                continue

            try:
                key = (
                    round(float(lon), self.coord_precision),
                    round(float(lat), self.coord_precision),
                )
            except (TypeError, ValueError):
                continue

            groups[key].append(raw)

        return groups

    def _build_hover_summary(
        self,
        *,
        place: str,
        service_count: int,
        entries: list[dict[str, Any]],
        unique_orgs: list[str],
    ) -> str:
        line1 = f"{place} ({service_count} services)" if service_count > 1 else place

        if len(unique_orgs) == 1:
            line2 = unique_orgs[0]
        elif not unique_orgs:
            line2 = "Unknown network"
        else:
            line2 = f"Multiple networks ({len(unique_orgs)})"

        unique_ports = self._unique_ports(entries)
        unique_procs = self._unique_processes(entries)

        ports_txt = self.format_list_compact([str(p) for p in unique_ports], max_items=3)

        if self.is_docker and self._has_only_placeholder_processes(unique_procs):
            procs_txt = "unavailable"
        else:
            procs_txt = self.format_list_compact(unique_procs, max_items=2)

        line3 = f"Ports: {ports_txt} | Procs: {procs_txt}"

        return f"{line1}<br>{line2}<br>{line3}"

    _SUMMARY_LABEL_WIDTH = len("Network operator:") + 1

    @classmethod
    def _format_summary_row(cls, label: str, icon: str, value: str) -> str:
        """Join a label, an already visually-padded icon, and a value into one row."""
        return f"{label.ljust(cls._SUMMARY_LABEL_WIDTH)}{icon} {value}"

    @staticmethod
    def _pick_country_code(entries: list[dict[str, Any]]) -> str | None:
        codes = [e.get("country_code") for e in entries if e.get("country_code")]
        return Counter(codes).most_common(1)[0][0] if codes else None

    @staticmethod
    def _display_verification_status(app: dict[str, Any]) -> str | None:
        """Return app_verification_status for display, substituting the pending sentinel.

        Only substitutes for a real application (exe is not None) - the
        synthetic unknown-application bucket has no pending work and must
        keep showing "unknown".
        """
        status = app.get("app_verification_status")
        if status is None and app.get("exe") is not None:
            return PENDING_VERIFICATION_STATUS
        return status

    @staticmethod
    def _pick_representative_app(
        entries: list[dict[str, Any]],
    ) -> tuple[str, str | None, list[dict[str, Any]], int]:
        """Select the representative application for a ServicePoint.

        Priority: failed, then unknown, then pending, then verified. Within
        a tier, the application present at the most entries wins; ties break
        alphabetically by display name. Applications with no app_name share
        one "Unknown" group. Each entry's applications dict may contain more
        than one application.

        Returns:
            (display name, verification_status, entries carrying that application, unique app count)
        """
        groups: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
        verification_status_by_key: dict[str | None, str | None] = {}

        for e in entries:
            applications = e.get("applications")
            apps = applications if isinstance(applications, dict) else {}
            seen_keys: set[str | None] = set()
            for app in apps.values():
                if not isinstance(app, dict):
                    continue
                name = app.get("app_name")
                key = name if isinstance(name, str) and name.strip() else None
                verification_status_by_key.setdefault(
                    key, ServicePointViewBuilder._display_verification_status(app)
                )
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                groups[key].append(e)

        if not groups:
            return "Unknown", None, [], 0

        def rank(item: tuple[str | None, list[dict[str, Any]]]) -> tuple[int, int, str]:
            key, group_entries = item
            verification_status = verification_status_by_key.get(key)
            display = key or "Unknown"
            return (
                _APP_VERIFICATION_STATUS_PRIORITY.get(verification_status, 1),
                -len(group_entries),
                display.lower(),
            )

        best_key, best_entries = min(groups.items(), key=rank)
        display_name = best_key or "Unknown"
        return display_name, verification_status_by_key.get(best_key), best_entries, len(groups)

    def _build_app_summary(
        self,
        *,
        place: str,
        country_code: str | None,
        entries: list[dict[str, Any]],
    ) -> str:
        app_name, app_verification_status, app_entries, unique_app_count = (
            self._pick_representative_app(entries)
        )
        app_extra = unique_app_count - 1
        apps_value = app_name if app_extra <= 0 else f"{app_name} +{app_extra}"

        orgs = self._unique_network_orgs(app_entries)
        org_value = orgs[0] if orgs else "Unknown network"

        location_row = self._format_summary_row("Location:", country_flag(country_code), place)
        operators_row = self._format_summary_row("Network operator:", "  ", org_value)
        apps_row = self._format_summary_row(
            "App:", f" {verification_status_glyph(app_verification_status)}", apps_value
        )

        return f"{location_row}<br>{operators_row}<br>{apps_row}"

    _VERIFICATION_STATUS_NOTE = "Verification status is evaluated by the operating system, not by TapMap."  # noqa: E501

    def _build_app_click_details(
        self,
        *,
        place: str,
        country_code: str | None,
        entries: list[dict[str, Any]],
    ) -> str:
        """Build the Non-Technical click-details panel: applications grouped by operator."""
        location_block = f"Location: {country_flag(country_code)} {place}"

        by_org = self._group_by_org(entries)
        org_blocks: list[str] = []
        for org in sorted(by_org.keys(), key=str.lower):
            apps = self._unique_applications(by_org[org])
            if not apps:
                continue
            lines = [f"Network operator: {org}"]
            for app in apps:
                bullet = verification_status_glyph(self._display_verification_status(app))
                lines.append(f"    {bullet} {self._format_app_line(app)}")
            org_blocks.append("\n".join(lines))

        return "\n\n".join([location_block, *org_blocks, self._VERIFICATION_STATUS_NOTE])

    @staticmethod
    def _unique_applications(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return each distinct-looking application in entries, once, verification-status-priority first."""  # noqa: E501
        by_exe: dict[str, dict[str, Any]] = {}
        for e in entries:
            applications = e.get("applications")
            apps = applications if isinstance(applications, dict) else {}
            for exe_key, app in apps.items():
                if isinstance(app, dict):
                    by_exe.setdefault(exe_key, app)

        def sort_key(app: dict[str, Any]) -> tuple[int, str]:
            verification_status = ServicePointViewBuilder._display_verification_status(app)
            name = app.get("app_name") or "Unknown application"
            return (_APP_VERIFICATION_STATUS_PRIORITY.get(verification_status, 1), name.lower())

        ordered = sorted(by_exe.values(), key=sort_key)

        # Different exe paths (e.g. OneDrive's several binaries) can share
        # every field _format_app_line displays.
        seen_display: set[tuple[Any, ...]] = set()
        unique: list[dict[str, Any]] = []
        for app in ordered:
            display_key = (
                app.get("app_name"),
                app.get("app_creator"),
                app.get("app_verification_status"),
                app.get("app_signature_state"),
                app.get("app_signature_state_details"),
            )
            if display_key in seen_display:
                continue
            seen_display.add(display_key)
            unique.append(app)

        return unique

    def _format_app_line(self, app: dict[str, Any]) -> str:
        name = app.get("app_name") or "Unknown application"
        display_status = self._display_verification_status(app)
        if display_status == PENDING_VERIFICATION_STATUS:
            creator = "Retrieving..."
        else:
            creator = app.get("app_creator") or "Unknown creator"
        color = verification_status_color(display_status)
        verification_status_text = (
            f'<span style="color:{color}">{self._verification_status_text(app)}</span>'
        )
        return f"{name} ({creator}, {verification_status_text})"

    @staticmethod
    def _verification_status_text(app: dict[str, Any]) -> str:
        """Return display text for an application's verification status.

        Uses the platform-specific signature state (humanized) and details
        when available. Falls back to the raw verification status otherwise.
        """
        display_status = ServicePointViewBuilder._display_verification_status(app)
        if display_status == PENDING_VERIFICATION_STATUS:
            return "Retrieving..."

        state = app.get("app_signature_state")
        if isinstance(state, str) and state.strip():
            humanized = humanize_camel_case(state.strip())
            details = app.get("app_signature_state_details")
            if isinstance(details, str) and details.strip() and details.strip().lower() != "none":
                return f"{humanized}: {details.strip()}"
            return humanized

        return safe_str(display_status) or "Unknown"

    _HEADER_LABEL_WIDTH = len("Coordinates:") + 2

    @classmethod
    def _format_header_line(cls, label: str, value: str) -> str:
        return f"{label.ljust(cls._HEADER_LABEL_WIDTH)}{value}"

    def _build_click_details(
        self,
        *,
        lon: float,
        lat: float,
        place: str,
        entries: list[dict[str, Any]],
        unique_orgs: list[str],
    ) -> str:
        unique_ips = self._unique_ips(entries)
        unique_ports = self._unique_ports(entries)
        unique_procs = self._unique_processes(entries)

        display_proc_count = (
            0 if self.is_docker and self._has_only_placeholder_processes(unique_procs)
            else len(unique_procs)
        )

        counts_value = (
            f"{len(entries)} | "
            f"Networks: {len(unique_orgs)} | "
            f"IPs: {len(unique_ips)} | "
            f"Ports: {len(unique_ports)} | "
            f"Procs: {display_proc_count}"
        )

        header = "\n".join(
            [
                self._format_header_line("Coordinates:", f"lon={lon}  lat={lat}"),
                self._format_header_line("Location:", place),
                self._format_header_line("Services:", counts_value),
            ]
        )

        process_note = ""
        if self.is_docker and self._has_only_placeholder_processes(unique_procs):
            process_note = "Process details unavailable in Docker mode.\n\n"

        org_blocks = self._build_org_blocks(entries)
        return f"{header}\n\n{process_note}" + "\n\n".join(org_blocks)

    @staticmethod
    def _pick_place(entries: list[dict[str, Any]]) -> str:
        cities = [e.get("city") for e in entries if e.get("city")]
        countries = [e.get("country") for e in entries if e.get("country")]

        city = Counter(cities).most_common(1)[0][0] if cities else None
        country = Counter(countries).most_common(1)[0][0] if countries else None

        if city and country:
            return f"{city}, {country}"
        if country:
            return str(country)
        return "Unknown place name"

    @staticmethod
    def _unique_str_field(entries: list[dict[str, Any]], key: str) -> list[str]:
        out: set[str] = set()
        for e in entries:
            v = e.get(key)
            if isinstance(v, str):
                s = v.strip()
                if s:
                    out.add(s)
        return sorted(out, key=str.lower)

    def _unique_network_orgs(self, entries: list[dict[str, Any]]) -> list[str]:
        return self._unique_str_field(entries, "asn_org")

    def _unique_ips(self, entries: list[dict[str, Any]]) -> list[str]:
        return self._unique_str_field(entries, "ip")

    @staticmethod
    def _unique_ports(entries: list[dict[str, Any]]) -> list[int]:
        ports: set[int] = set()
        for e in entries:
            p = e.get("port")
            if isinstance(p, int) and p > 0:
                ports.add(p)
        return sorted(ports)

    @staticmethod
    def _unique_processes(entries: list[dict[str, Any]]) -> list[str]:
        out: set[str] = set()
        for e in entries:
            applications = e.get("applications")
            apps = applications if isinstance(applications, dict) else {}
            for app in apps.values():
                if not isinstance(app, dict):
                    continue
                procs = app.get("processes")
                if not isinstance(procs, list):
                    continue
                for p in procs:
                    if isinstance(p, str):
                        s = p.strip()
                        if s:
                            out.add(s)
        return sorted(out, key=str.lower)
    
    @staticmethod
    def _has_only_placeholder_processes(processes: list[str]) -> bool:
        """Return True if process names only contain placeholder values."""
        cleaned = [p.strip() for p in processes if isinstance(p, str) and p.strip()]
        if not cleaned:
            return True
        return set(cleaned) <= {"System"}

    @staticmethod
    def _group_by_org(entries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        by_org: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for e in entries:
            org_val = e.get("asn_org")
            org = (
                org_val.strip()
                if isinstance(org_val, str) and org_val.strip()
                else "Unknown network"
            )
            by_org[org].append(e)
        return by_org

    def _build_org_blocks(self, entries: list[dict[str, Any]]) -> list[str]:
        by_org = self._group_by_org(entries)

        blocks: list[str] = []
        for org in sorted(by_org.keys(), key=str.lower):
            org_entries = sorted(by_org[org], key=self._service_sort_key)
            blocks.append(self._format_org_block(org, org_entries))

        return blocks

    @staticmethod
    def _service_sort_key(e: dict[str, Any]) -> tuple[str, int]:
        ip = e.get("ip")
        ip_txt = ip if isinstance(ip, str) else ""
        port = e.get("port")
        port_i = port if isinstance(port, int) else 0
        return (ip_txt, port_i)

    _PROC_LABEL_WIDTH = len("Executable:") + 2

    def _format_org_block(self, org: str, org_entries: list[dict[str, Any]]) -> str:
        lines: list[str] = [org]

        for e in org_entries:
            ip = safe_str(e.get("ip")) or "?"
            port_val = e.get("port")
            port = port_val if isinstance(port_val, int) else 0

            proto = self._safe_proto(e.get("proto"))
            addr = self._fmt_ip_port(ip, port)

            lines.append(f"    {addr} ({proto})")
            lines.extend(self._format_process_blocks(e))

        return "\n".join(lines)

    @classmethod
    def _format_label(cls, label: str, value: str) -> str:
        return f"        {label.ljust(cls._PROC_LABEL_WIDTH)}{value}"

    def _display_exe(self, exe_key: str) -> str:
        """Return the Executable: line value: elided path, wrapped for click-to-reveal.

        The full path is embedded as a "full" attribute for modal_view to turn
        into a clickable, tooltip-bearing component. Safe unescaped, since
        Windows paths (the only exe_key source today) cannot contain '"'.
        """
        if exe_key == self._UNKNOWN_APP_KEY:
            return "Unknown"
        return f'<exe full="{exe_key}">{elide_path_middle(exe_key)}</exe>'

    def _format_process_blocks(self, entry: dict[str, Any]) -> list[str]:
        """Build one Process:/App:/Executable: block per application at a connection."""
        if self.is_docker:
            proc_names = self._unique_processes([entry])
            if self._has_only_placeholder_processes(proc_names):
                return [self._format_label("Process:", "unavailable")]

        applications = entry.get("applications")
        apps = applications if isinstance(applications, dict) else {}

        items = sorted(
            ((k, v) for k, v in apps.items() if isinstance(v, dict)),
            key=lambda kv: ((kv[1].get("app_name") or "").lower(), kv[0]),
        )

        lines: list[str] = []
        for i, (exe_key, app) in enumerate(items):
            if i > 0:
                lines.append("")
            lines.append(self._format_label("Process:", self._format_proc_names(app)))
            lines.append(
                self._format_label("App:", app.get("app_name") or "Unknown application")
            )
            lines.append(self._format_label("Executable:", self._display_exe(exe_key)))

        return lines

    @staticmethod
    def _format_proc_names(app: dict[str, Any]) -> str:
        """Format one application's process names and PIDs as 'name (pid X, Y), ...'."""
        processes = app.get("processes")
        procs = processes if isinstance(processes, list) else []
        proc_pids_raw = app.get("proc_pids")
        proc_pids: dict[str, list[int]] = (
            proc_pids_raw if isinstance(proc_pids_raw, dict) else {}
        )

        names = sorted(
            {p.strip() for p in procs if isinstance(p, str) and p.strip()}, key=str.lower
        )
        if not names:
            return "-"

        parts: list[str] = []
        for name in names:
            pids_raw = proc_pids.get(name)
            pids = (
                sorted({x for x in pids_raw if isinstance(x, int) and x > 0})
                if isinstance(pids_raw, list)
                else []
            )
            if pids:
                parts.append(f"{name} (pid {', '.join(str(x) for x in pids)})")
            else:
                parts.append(name)

        return ", ".join(parts)

