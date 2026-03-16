"""Modal content rendering for the TapMap UI.

Build Dash components for menu actions, map clicks,
and modal screens shown by the application.
"""

from __future__ import annotations

from typing import Any

from dash import dcc, html

from ui.about_view import render_about
from ui.formatting import (
    port_from_local,
    pretty_bind_ip,
    safe_int,
    safe_str,
    scope_rank,
    strip_port,
)
from ui.help_view import render_help
from ui.tables import ColumnSpec, build_table, cell


class ModalTextBuilder:
    """Build modal content for menu actions and map clicks.

    All methods return Dash components, not raw strings.
    """

    def __init__(self, app_name: str, app_version: str, app_author: str) -> None:
        self.app_name = app_name
        self.app_version = app_version
        self.app_author = app_author

        self._label_map: dict[str, str] = {
            "menu_unmapped": "Show unmapped public services",
            "menu_lan_local": "Show established LAN/LOCAL services",
            "menu_open_ports": "Show open ports",
            "menu_cache_terminal": "Show cache in terminal",
            "menu_clear_cache": "Clear cache",
            "menu_help": "Help",
            "menu_about": "About",
        }

    def for_action(
        self,
        action: str,
        *,
        snapshot: Any | None = None,
        show_system: bool = False,
    ) -> list[Any]:
        """Build modal body content for a menu action.

        Args:
            action: Menu action ID.
            snapshot: Latest model snapshot (dict) or None.
            show_system: Open ports view toggle state.

        Returns:
            Dash components for the modal body.
        """
        if action == "menu_unmapped":
            return self._render_unmapped(snapshot)

        if action == "menu_lan_local":
            return self._render_lan_local(snapshot)

        if action == "menu_open_ports":
            return self._render_open_ports(snapshot, show_system=show_system)

        if action == "menu_help":
            return render_help()

        if action == "menu_about":
            return render_about(
                app_name=self.app_name,
                app_version=self.app_version,
                app_author=self.app_author,
                snapshot=snapshot,
            )

        label = self._label_map.get(action, action)
        return [self._h1("Details"), html.Pre(f"Menu selected: {label}")]

    def for_click(self, click_data: Any, ui_view: Any) -> html.Pre | None:
        """Build click detail content from Plotly clickData.

        Args:
            click_data: Plotly clickData payload.
            ui_view: Dash store content with the "details" mapping.

        Returns:
            html.Pre for a valid click, otherwise None.
        """
        if not isinstance(click_data, dict):
            return None

        points = click_data.get("points")
        if not isinstance(points, list) or not points:
            return None

        point0 = points[0]
        if not isinstance(point0, dict):
            return None

        idx = self.first_idx(point0.get("customdata"))
        if idx is None:
            return None

        view = ui_view if isinstance(ui_view, dict) else {}
        details = view.get("details")
        details_map = details if isinstance(details, dict) else {}

        detail = details_map.get(str(idx), f"Location {idx}")
        lon = point0.get("lon")
        lat = point0.get("lat")

        body_text = f"lon={lon}  lat={lat}\n\n{detail}"
        return html.Pre(body_text)

    # ---------- Common UI helpers ----------

    @staticmethod
    def _h1(title: str) -> html.H1:
        return html.H1(title)

    @classmethod
    def _open_ports_sort_key(cls, row: dict[str, Any]) -> tuple[int, int, int, str, int]:
        """Return sort key for Open Ports rows."""
        bind_scope = safe_str(row.get("bind_scope")).upper()
        proto = safe_str(row.get("proto")).upper()
        local_address = safe_str(row.get("local_address"))

        port = port_from_local(local_address)
        port = port if port >= 0 else 65536

        process_name = safe_str(row.get("process_label") or row.get("process_name")).lower()
        pid = safe_int(row.get("pid"))

        scope_order = {
            "PUBLIC": 0,
            "LAN": 1,
            "LOCAL": 2,
        }.get(bind_scope, 3)

        proto_order = 0 if proto == "TCP" else 1

        return (scope_order, proto_order, port, process_name, pid)

    @staticmethod
    def _is_system_process(row: dict[str, Any]) -> bool:
        """Return True if the row should be treated as a system process."""
        process_status = safe_str(row.get("process_status"))
        process_name = safe_str(row.get("process_name") or row.get("process_label")).lower()

        hidden = {
            "system",
            "svchost.exe",
            "lsass.exe",
            "wininit.exe",
            "services.exe",
            "spoolsv.exe",
        }

        return process_status != "OK" or process_name in hidden

    @classmethod
    def _render_open_ports(
        cls,
        snapshot: Any | None,
        *,
        show_system: bool,
    ) -> list[Any]:
        """Build modal content for the Open Ports view."""
        snap = snapshot if isinstance(snapshot, dict) else {}
        rows = snap.get("open_ports")
        rows_list = rows if isinstance(rows, list) else []
        cleaned: list[dict[str, Any]] = [r for r in rows_list if isinstance(r, dict)]

        if not show_system:
            filtered: list[dict[str, Any]] = []
            for r in cleaned:
                if cls._is_system_process(r):
                    continue
                filtered.append(r)
            cleaned = filtered

        cleaned.sort(key=cls._open_ports_sort_key)

        toggle = dcc.Checklist(
            id="toggle_open_ports_system",
            options=[{"label": "Show system processes", "value": "on"}],
            value=(["on"] if show_system else []),
            className="mx-title-toggle",
        )

        header = [
            html.H1(
                children=[html.Span("Open ports (TCP LISTEN and UDP bound)"), toggle],
                className="mx-h1-with-toggle",
            )
        ]

        if not cleaned:
            return [*header, html.Pre("(no open ports found)")]

        body_rows: list[Any] = []
        for r in cleaned:
            full_local = safe_str(r.get("local_address"))
            ip_display = pretty_bind_ip(strip_port(full_local))

            service = safe_str(r.get("service"))
            service_hint = safe_str(r.get("service_hint")) or None

            process_label = safe_str(r.get("process_label") or r.get("process_name"))
            process_hint = safe_str(r.get("process_hint")) or None
            process_status = safe_str(r.get("process_status")) or None

            if not process_label:
                process_label = process_status or "Unavailable"
            if process_hint is None:
                process_hint = process_status

            pid_value = r.get("pid")
            pid_text = str(safe_int(pid_value)) if pid_value is not None else ""

            body_rows.append(
                html.Tr(
                    [
                        cell(safe_str(r.get("bind_scope"))),
                        cell(safe_str(r.get("proto"))),
                        cell(str(port_from_local(full_local))),
                        cell(ip_display, title=full_local),
                        cell(service, title=service_hint),
                        cell(pid_text),
                        cell(process_label, title=process_hint),
                    ]
                )
            )

        columns = [
            ColumnSpec("Bind scope", "8.0%"),
            ColumnSpec("Proto", "8.0%"),
            ColumnSpec("Port", "8.0%"),
            ColumnSpec("Local IP", "24.0%"),
            ColumnSpec("Port service", "20.0%"),
            ColumnSpec("PID", "8.0%"),
            ColumnSpec("Process", "24.0%"),
        ]

        table = build_table(
            class_name="mx-table mx-open-ports",
            columns=columns,
            header_cells=[c.header for c in columns],
            body_rows=body_rows,
        )

        return [*header, table]

    # Helpers for unmapped and LAN/LOCAL services views
    @staticmethod
    def _process_text(row: dict[str, Any]) -> tuple[str, str | None]:
        """Return process label and tooltip."""
        label = safe_str(row.get("process_name"))
        if not label:
            label = safe_str(row.get("process_status")) or "Unavailable"

        exe = row.get("exe")
        if isinstance(exe, str) and exe.strip():
            return label, exe.strip()

        status = row.get("process_status")
        if isinstance(status, str) and status.strip():
            return label, status.strip()

        return label, None

    @staticmethod
    def _service_text(row: dict[str, Any]) -> tuple[str, str | None]:
        """Return service label and tooltip."""
        service = safe_str(row.get("service")) or "Unknown"
        hint = safe_str(row.get("service_hint")) or None
        return service, hint

    @classmethod
    def _aggregate_service_rows(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Aggregate service rows by scope, ip, port, pid and process."""
        agg: dict[tuple[str, str, int, int, str], dict[str, Any]] = {}

        for r in rows:
            ip = safe_str(r.get("ip"))
            port = safe_int(r.get("port"), default=-1)
            scope = safe_str(r.get("service_scope")) or "UNKNOWN"

            pid_val = r.get("pid")
            pid = safe_int(pid_val) if pid_val is not None else -1

            proc_label, proc_tip = cls._process_text(r)
            svc_val, svc_tip = cls._service_text(r)

            key = (scope, ip, port, pid, proc_label)
            entry = agg.get(key)

            if entry is None:
                agg[key] = {
                    "scope": scope,
                    "ip": ip,
                    "port": port,
                    "service": svc_val,
                    "service_tip": svc_tip,
                    "pid": pid if pid != -1 else None,
                    "process": proc_label,
                    "process_tip": proc_tip,
                    "count": 1,
                }
            else:
                entry["count"] = int(entry.get("count") or 0) + 1
                if entry.get("process_tip") in {None, ""} and proc_tip:
                    entry["process_tip"] = proc_tip
                if entry.get("service_tip") in {None, ""} and svc_tip:
                    entry["service_tip"] = svc_tip

        return list(agg.values())

    @staticmethod
    def _service_sort_key(row: dict[str, Any]) -> tuple[int, int, int, str, str]:
        """Return sort key for aggregated service rows."""
        interesting_ports = {443, 53, 80, 3478, 22, 3389}

        scope = safe_str(row.get("scope"))
        port = safe_int(row.get("port"), default=-1)
        proc = safe_str(row.get("process"))
        ip = safe_str(row.get("ip"))
        count = safe_int(row.get("count"), default=0)

        port_rank = 0 if port in interesting_ports else 1
        return (scope_rank(scope), port_rank, -count, proc.lower(), ip)

    @classmethod
    def _build_service_body_rows(cls, aggregated: list[dict[str, Any]]) -> list[Any]:
        """Build table rows for aggregated service entries."""
        body_rows: list[Any] = []

        for row in sorted(aggregated, key=cls._service_sort_key):
            scope = safe_str(row.get("scope"))
            ip = safe_str(row.get("ip"))
            port = safe_int(row.get("port"), default=-1)

            service = safe_str(row.get("service")) or "Unknown"
            service_tip = safe_str(row.get("service_tip")) or None

            pid_val = row.get("pid")
            pid_txt = str(safe_int(pid_val)) if pid_val is not None else ""

            proc = safe_str(row.get("process"))
            proc_tip = safe_str(row.get("process_tip")) or None

            count = safe_int(row.get("count"), default=1)

            body_rows.append(
                html.Tr(
                    [
                        cell(scope),
                        cell(ip or "-"),
                        cell(str(port) if port > 0 else "-"),
                        cell(service, title=service_tip),
                        cell(str(count)),
                        cell(pid_txt),
                        cell(proc, title=proc_tip),
                    ]
                )
            )

        return body_rows

    @classmethod
    def _build_service_table(
        cls,
        aggregated: list[dict[str, Any]],
        *,
        class_name: str,
    ) -> html.Table:
        """Build a service table for aggregated rows."""
        columns = [
            ColumnSpec("Scope", "8%"),
            ColumnSpec("Remote IP", "28%"),
            ColumnSpec("Port", "8%"),
            ColumnSpec("Port service", "16%"),
            ColumnSpec("Count", "8%"),
            ColumnSpec("PID", "8%"),
            ColumnSpec("Process", "24%"),
        ]

        return build_table(
            class_name=class_name,
            columns=columns,
            header_cells=[c.header for c in columns],
            body_rows=cls._build_service_body_rows(aggregated),
        )

    @classmethod
    def _render_unmapped(cls, snapshot: Any | None) -> list[Any]:
        """Render unmapped services.

        Render established TCP services with PUBLIC service_scope and missing geolocation.
        """
        snap = snapshot if isinstance(snapshot, dict) else {}
        items = snap.get("cache_items")
        rows = items if isinstance(items, list) else []

        cleaned: list[dict[str, Any]] = [r for r in rows if isinstance(r, dict)]

        def has_geo(r: dict[str, Any]) -> bool:
            lat = r.get("lat")
            lon = r.get("lon")
            return isinstance(lat, (int, float)) and isinstance(lon, (int, float))

        filtered: list[dict[str, Any]] = []
        for r in cleaned:
            scope = safe_str(r.get("service_scope")) or "UNKNOWN"
            geo_ok = has_geo(r)
            if scope == "PUBLIC" and not geo_ok:
                filtered.append(r)

        header = html.H1("Unmapped public services (missing geolocation)", className="mx-h1")

        if not filtered:
            return [header, html.Pre("(no unmapped public services)")]

        aggregated = cls._aggregate_service_rows(filtered)
        table = cls._build_service_table(
            aggregated,
            class_name="mx-table mx-unmapped",
        )

        return [header, table]

    # LAN/LOCAL services view
    @classmethod
    def _render_lan_local(cls, snapshot: Any | None) -> list[Any]:
        """Render LAN and LOCAL established services."""
        snap = snapshot if isinstance(snapshot, dict) else {}
        items = snap.get("cache_items")
        rows = items if isinstance(items, list) else []

        cleaned: list[dict[str, Any]] = [r for r in rows if isinstance(r, dict)]

        def is_established_tcp(row: dict[str, Any]) -> bool:
            state = row.get("state")
            if isinstance(state, str) and state.strip() and state.strip().upper() != "ESTABLISHED":
                return False

            proto = row.get("proto")
            return not (isinstance(proto, str) and proto.strip() and proto.strip().lower() != "tcp")

        filtered: list[dict[str, Any]] = []
        for r in cleaned:
            scope = safe_str(r.get("service_scope")) or "UNKNOWN"
            if scope in {"LAN", "LOCAL"} and is_established_tcp(r):
                filtered.append(r)

        header = html.H1("Established LAN/LOCAL services", className="mx-h1")

        if not filtered:
            return [header, html.Pre("(no LAN/LOCAL services)")]

        aggregated = cls._aggregate_service_rows(filtered)
        table = cls._build_service_table(
            aggregated,
            class_name="mx-table mx-lan-local",
        )

        return [header, table]

    def missing_geo_db(self, geo_data_dir: str) -> list[Any]:
        """Render the Missing GeoIP databases view."""
        return [
            self._h1("Missing GeoIP databases"),
            html.P(
                [
                    "TapMap can run without geolocation, but GeoIP lookups will be disabled. ",
                    "To enable geolocation, download the GeoLite2 databases and place them in "
                    "this folder:",
                ]
            ),
            html.Div(
                className="mx-path-row",
                children=[
                    html.Pre(geo_data_dir, className="mx-path-box"),
                    html.Button(
                        "Open data folder",
                        id="btn_open_data",
                        n_clicks=0,
                        className="mx-btn mx-btn--primary mx-btn--nowrap",
                        type="button",
                    ),
                    html.Button(
                        "Recheck databases",
                        id="btn_check_databases",
                        n_clicks=0,
                        className="mx-btn mx-btn--primary mx-btn--nowrap",
                        type="button",
                    ),
                ],
            ),
            html.P("Required files:"),
            html.Ul(
                [
                    html.Li("GeoLite2-ASN.mmdb"),
                    html.Li("GeoLite2-City.mmdb"),
                ]
            ),
            html.H2("Steps"),
            html.Ol(
                [
                    html.Li("Open the data folder."),
                    html.Li("Copy the GeoLite2 .mmdb files into the folder."),
                    html.Li("Click Recheck GeoIP databases in the app."),
                ]
            ),
            html.H2("Download"),
            html.P(
                [
                    "Download is free from MaxMind, but requires an account and "
                    "acceptance of license terms. ",
                    "Create a free account and download the databases here: ",
                    html.A(
                        "MaxMind GeoLite2 download page",
                        href="https://dev.maxmind.com/geoip/geolite2-free-geolocation-data",
                        target="_blank",
                        rel="noopener noreferrer",
                    ),
                    ".",
                ]
            ),
            html.P(
                "Update recommendation: download updated databases regularly (for example monthly)."
            ),
        ]

    # ---------- Click helpers ----------

    @staticmethod
    def first_idx(customdata: Any) -> int | None:
        """Extract a service index from Plotly customdata.

        Supported forms:
            - dict with keys {"kind", "idx"}
            - integer
            - nested list or tuple structures
        """
        if isinstance(customdata, dict):
            if customdata.get("kind") in {"target", "line"}:
                idx = customdata.get("idx")
                return idx if isinstance(idx, int) else None
            return None

        if isinstance(customdata, int):
            return customdata

        if isinstance(customdata, (list, tuple)) and customdata:
            return ModalTextBuilder.first_idx(customdata[0])

        return None
