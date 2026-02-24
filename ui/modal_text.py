from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from typing import Any

from dash import dcc, html

from ui.help_text import HELP_CONTENT


class ModalTextBuilder:
    """Build modal content for menu actions and map clicks.

    All methods return Dash components, not raw strings.
    """

    def __init__(self, app_name: str, app_version: str, app_author: str) -> None:
        self.app_name = app_name
        self.app_version = app_version
        self.app_author = app_author

        self._label_map: dict[str, str] = {
            "menu_unmapped": "Show unmapped endpoints",
            "menu_lan_local": "Show LAN and LOCAL connections",
            "menu_open_ports": "Show open ports",
            "menu_cache_terminal": "Show cache in terminal",
            "menu_clear": "Clear cache",
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
            return self._render_help()

        if action == "menu_about":
            return self._render_about(snapshot)

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

        detail = details_map.get(str(idx), f"Endpoint {idx}")
        lon = point0.get("lon")
        lat = point0.get("lat")

        body_text = f"lon={lon}  lat={lat}\n\n{detail}"
        return html.Pre(body_text)

    # ---------- Common UI helpers ----------

    @staticmethod
    def _h1(title: str) -> html.H1:
        return html.H1(title)

    @staticmethod
    def _kv_table(rows: Iterable[tuple[str, str]]) -> html.Table:
        """Render a two-column key/value table with tooltips."""
        body: list[Any] = []
        for key, value in rows:
            v = "" if value is None else str(value)
            body.append(
                html.Tr(
                    [
                        html.Td(key),
                        html.Td(html.Span(v, title=v if v else None)),
                    ]
                )
            )
        colgroup = html.Colgroup(
            [
                html.Col(style={"width": "180px"}),
                html.Col(),
            ]
        )

        return html.Table(
            className="mx-table mx-info-table",
            children=[colgroup, html.Tbody(body)],
        )

    @staticmethod
    def _cell(text: str, title: str | None = None) -> html.Td:
        """Render a table cell with truncation and a tooltip.

        Use the full value as the default tooltip.
        """
        value = text or ""
        tooltip = title if title is not None else value
        tooltip = tooltip if tooltip else None
        return html.Td(html.Span(value, className="mx-cell-text", title=tooltip))

    @staticmethod
    def _safe_str(value: Any) -> str:
        return "" if value is None else str(value)

    @staticmethod
    def _safe_int(value: Any, default: int = -1) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    # ---------- Help ----------

    def _render_help(self) -> list[Any]:
        """Render Help content.

        Add an H1 when HELP_CONTENT does not start with one.
        """
        content = HELP_CONTENT
        items = content if isinstance(content, list) else [content]

        if items and isinstance(items[0], html.H1):
            return items

        return [self._h1("Help"), *items]

    # ---------- About ----------

    def _render_about(self, snapshot: Any | None = None) -> list[Any]:
        """Render the About view.

        Read snapshot["app_info"] only and avoid network calls.
        """
        app_info: dict[str, Any] = {}
        if isinstance(snapshot, dict):
            info = snapshot.get("app_info")
            if isinstance(info, dict):
                app_info = info

        poll_ms = app_info.get("poll_interval_ms")
        coord_precision = app_info.get("coord_precision")
        near_km = app_info.get("zoom_near_km")

        geoinfo_enabled = bool(app_info.get("geoinfo_enabled", False))
        geo_data_dir = (
            app_info.get("geo_data_dir") if isinstance(app_info.get("geo_data_dir"), str) else ""
        )

        myloc_mode = (
            app_info.get("myloc_mode") if isinstance(app_info.get("myloc_mode"), str) else "OFF"
        )
        my_location = app_info.get("my_location")

        public_ip_cached = app_info.get("public_ip_cached")
        public_ip_cached = (
            public_ip_cached if isinstance(public_ip_cached, str) and public_ip_cached else None
        )

        auto_geo_cached = app_info.get("auto_geo_cached")
        auto_geo = auto_geo_cached if isinstance(auto_geo_cached, dict) else {}

        os_text = app_info.get("os") if isinstance(app_info.get("os"), str) else "-"
        py_text = app_info.get("python") if isinstance(app_info.get("python"), str) else "-"

        net_backend_val = app_info.get("net_backend")
        net_backend = net_backend_val if isinstance(net_backend_val, str) else "-"
        net_backend_version_val = app_info.get("net_backend_version")
        net_backend_version = (
            net_backend_version_val if isinstance(net_backend_version_val, str) else "-"
        )

        tapmap_rows: list[tuple[str, str]] = [
            ("Name", self.app_name),
            ("Version", self.app_version),
            ("Author", self.app_author),
            ("Poll interval", f"{poll_ms} ms" if isinstance(poll_ms, int) else "-"),
            ("Coord precision", str(coord_precision) if coord_precision is not None else "-"),
            ("Near distance", f"{near_km} km" if isinstance(near_km, (int, float)) else "-"),
        ]

        geo_rows: list[tuple[str, str]] = [
            ("Geolocation", "Enabled" if geoinfo_enabled else "Disabled"),
            ("GeoIP data folder", geo_data_dir if geo_data_dir else "-"),
        ]

        location_rows = self._build_location_rows(
            myloc_mode,
            my_location,
            public_ip_cached,
            auto_geo,
        )

        runtime_rows: list[tuple[str, str]] = [
            ("OS", os_text),
            ("Python", py_text),
            ("Network backend", net_backend),
            ("Backend version", net_backend_version),
        ]

        return [
            self._h1(f"About {self.app_name}"),
            html.P(
                "TapMap combines local socket inspection, IP geolocation, "
                "and interactive map visualization."
            ),
            html.P(
                "It reads active network connections using a platform specific backend, "
                "MaxMind GeoLite2 databases for geolocation, "
                "and Dash with Plotly for map rendering."
            ),
            html.P("All processing is local. TapMap does not inspect traffic contents."),
            self._kv_table(tapmap_rows),
            html.H2("Geolocation"),
            html.P(
                "Geolocation is based on local MaxMind GeoLite2 .mmdb databases. "
                "The databases are not included."
            ),
            self._kv_table(geo_rows),
            html.Div(
                className="mx-path-row",
                children=[
                    html.Pre(geo_data_dir, className="mx-path-box") if geo_data_dir else None,
                    html.Button(
                        "Open data folder",
                        id="btn_open_data",
                        n_clicks=0,
                        className="mx-btn mx-btn--primary mx-btn--nowrap",
                        type="button",
                    ),
                    html.Button(
                        "Recheck GeoIP databases",
                        id="btn_check_databases",
                        n_clicks=0,
                        className="mx-btn mx-btn--primary mx-btn--nowrap",
                        type="button",
                    ),
                ],
            ),
            html.H2("Location"),
            self._kv_table(location_rows),
            html.H2("Runtime"),
            self._kv_table(runtime_rows),
            html.H2("Project"),
            html.P("TapMap is free and open source."),
            html.Ul(
                [
                    html.Li(
                        html.A(
                            "Project page on GitHub",
                            href="https://github.com/olalie/",
                            target="_blank",
                            rel="noopener noreferrer",
                        )
                    ),
                    html.Li(
                        html.A(
                            "MaxMind GeoLite2 project",
                            href="https://dev.maxmind.com/geoip/geolite2-free-geolocation-data",
                            target="_blank",
                            rel="noopener noreferrer",
                        )
                    ),
                    html.Li(
                        html.A(
                            "Buy Me a Coffee",
                            href="https://www.buymeacoffee.com/olalie",
                            target="_blank",
                            rel="noopener noreferrer",
                        )
                    ),
                ]
            ),
        ]

    @classmethod
    def _build_location_rows(
        cls,
        myloc_mode: str,
        my_location: Any,
        public_ip_cached: str | None,
        auto_geo: dict[str, Any],
    ) -> list[tuple[str, str]]:
        """Build Location section rows for the MY_LOCATION mode.

        Modes:
            OFF: local marker disabled
            FIXED: fixed lon/lat
            AUTO: cached public IP and geo place and coordinates
            AUTO (NO GEO): cached public IP and unavailable geo data
        """
        if myloc_mode == "OFF":
            return [("MY_LOCATION", "none (local marker hidden)")]

        if myloc_mode == "FIXED":
            if isinstance(my_location, (list, tuple)) and len(my_location) == 2:
                lon, lat = my_location[0], my_location[1]
                return [("MY_LOCATION", cls._fmt_coord(lon, lat))]
            return [("MY_LOCATION", "fixed (invalid value)")]

        rows: list[tuple[str, str]] = [("MY_LOCATION", "auto")]
        rows.append(("Public IP", public_ip_cached or "-"))

        if myloc_mode == "AUTO":
            place = cls._fmt_place(auto_geo.get("city"), auto_geo.get("country"))
            coord = cls._fmt_coord(auto_geo.get("lon"), auto_geo.get("lat"))
            rows.append(("AUTO place", place))
            rows.append(("AUTO coordinate", coord))
            return rows

        rows.append(("AUTO geo", "not available"))
        return rows

    @staticmethod
    def _fmt_coord(lon: Any, lat: Any) -> str:
        if isinstance(lon, (int, float)) and isinstance(lat, (int, float)):
            return f"{float(lon)}, {float(lat)}"
        return "-"

    @staticmethod
    def _fmt_place(city: Any, country: Any) -> str:
        c = city.strip() if isinstance(city, str) else ""
        k = country.strip() if isinstance(country, str) else ""
        if c and k:
            return f"{c}, {k}"
        if k:
            return k
        return "-"

    # ---------- Open ports ----------

    @staticmethod
    def _scope_rank(scope: str) -> int:
        order = {"PUBLIC": 0, "LAN": 1, "LOCAL": 2}
        return order.get(scope.upper(), 9)

    @staticmethod
    def _proto_rank(proto: str) -> int:
        p = proto.lower()
        if p == "tcp":
            return 0
        if p == "udp":
            return 1
        return 9

    @staticmethod
    def _port_from_local(addr: str) -> int:
        try:
            return int(addr.rsplit(":", 1)[-1])
        except (ValueError, TypeError):
            return -1

    @staticmethod
    def _strip_port(addr: str) -> str:
        """Strip a trailing ':port' from an address.

        Examples:
            '127.0.0.1:8050' -> '127.0.0.1'
            '[::1]:49870'    -> '::1'
            '[::]:53'        -> '::'
            '0.0.0.0:80'     -> '0.0.0.0'
        """
        if not addr:
            return ""

        s = addr.strip()

        if s.startswith("["):
            end = s.find("]")
            return s[1:end].strip() if end != -1 else s

        if s.count(":") == 1:
            return s.rsplit(":", 1)[0].strip()

        return s

    @staticmethod
    def _pretty_bind_ip(ip: str) -> str:
        if ip == "0.0.0.0":
            return "ALL (IPv4)"
        if ip == "::":
            return "ALL (IPv6)"
        return ip

    @classmethod
    def _open_ports_sort_key(cls, row: dict[str, Any]) -> tuple[int, int, int, str, int]:
        """Return sort key for Open Ports rows."""
        scope = cls._safe_str(row.get("scope")).upper()
        proto = cls._safe_str(row.get("proto")).upper()
        local_address = cls._safe_str(row.get("local_address"))

        port = cls._port_from_local(local_address)

        process_name = cls._safe_str(
            row.get("process_label") or row.get("process_name")
        ).lower()

        pid = cls._safe_int(row.get("pid"))

        scope_order = {
            "PUBLIC": 0,
            "LAN": 1,
            "LOCAL": 2,
        }.get(scope, 3)

        proto_order = 0 if proto == "TCP" else 1

        return (scope_order, proto_order, port, process_name, pid)
    
    @staticmethod
    def _is_system_process(process_name: str) -> bool:
        """Return True if process is a core Windows system service."""
        hidden = {
            "system",
            "svchost.exe",
            "lsass.exe",
            "wininit.exe",
            "services.exe",
            "spoolsv.exe",
        }
        return process_name.lower() in hidden

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
                process_name = cls._safe_str(r.get("process_name") or r.get("process_label"))
                if cls._is_system_process(process_name):
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
            full_local = cls._safe_str(r.get("local_address"))
            ip_display = cls._pretty_bind_ip(cls._strip_port(full_local))

            service = cls._safe_str(r.get("service"))
            service_hint = cls._safe_str(r.get("service_hint")) or None

            process_label = cls._safe_str(r.get("process_label") or r.get("process_name"))
            process_hint = cls._safe_str(r.get("process_hint")) or None
            process_status = cls._safe_str(r.get("process_status")) or None

            if not process_label:
                process_label = process_status or "Unavailable"
            if process_hint is None:
                process_hint = process_status

            pid_value = r.get("pid")
            pid_text = str(cls._safe_int(pid_value)) if pid_value is not None else ""

            body_rows.append(
                html.Tr(
                    [
                        cls._cell(cls._safe_str(r.get("scope"))),
                        cls._cell(cls._safe_str(r.get("proto"))),
                        cls._cell(str(cls._port_from_local(full_local))),
                        cls._cell(ip_display, title=full_local),
                        cls._cell(service, title=service_hint),
                        cls._cell(pid_text),
                        cls._cell(process_label, title=process_hint),
                    ]
                )
            )

        colgroup = html.Colgroup(
            [
                html.Col(style={"width": "8.0%"}),   # Scope
                html.Col(style={"width": "8.0%"}),   # Proto
                html.Col(style={"width": "8.0%"}),   # Port
                html.Col(style={"width": "24.0%"}),  # Local IP
                html.Col(style={"width": "20.0%"}),  # Port service
                html.Col(style={"width": "8.0%"}),   # PID
                html.Col(style={"width": "24.0%"}),  # Process
            ]
        )

        table = html.Table(
            className="mx-table mx-open-ports",
            children=[
                colgroup,
                html.Thead(
                    html.Tr(
                        [
                            html.Th("Scope"),
                            html.Th("Proto"),
                            html.Th("Port"),
                            html.Th("Local IP"),
                            html.Th("Port service"),
                            html.Th("PID"),
                            html.Th("Process"),
                        ]
                    )
                ),
                html.Tbody(body_rows),
            ],
        )
        return [*header, table]

    # ---------- Unmapped endpoints ----------

    @staticmethod
    def _remote_scope(ip: str | None) -> str:
        """Classify a remote IP for display in the Unmapped table.

        LOCAL: loopback
        LAN: private or link-local
        PUBLIC: everything else
        UNKNOWN: missing/invalid
        """
        if not ip:
            return "UNKNOWN"

        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return "UNKNOWN"

        if addr.is_loopback:
            return "LOCAL"

        if addr.is_private or addr.is_link_local:
            return "LAN"

        return "PUBLIC"

    @classmethod
    def _render_unmapped(cls, snapshot: Any | None) -> list[Any]:
        """Render unmapped endpoints.

        Render established TCP endpoints with PUBLIC remote IPs and missing geolocation.
        """
        snap = snapshot if isinstance(snapshot, dict) else {}
        items = snap.get("cache_items")
        rows = items if isinstance(items, list) else []

        cleaned: list[dict[str, Any]] = [r for r in rows if isinstance(r, dict)]

        def has_geo(r: dict[str, Any]) -> bool:
            lat = r.get("lat")
            lon = r.get("lon")
            return isinstance(lat, (int, float)) and isinstance(lon, (int, float))

        # 1) Filter to "unmapped" candidates (PUBLIC only)
        filtered: list[dict[str, Any]] = []
        for r in cleaned:
            ip = r.get("ip")
            scope = cls._remote_scope(ip)
            geo_ok = has_geo(r)

            if scope == "PUBLIC" and not geo_ok:
                filtered.append(r)

        header = html.H1("Unmapped public endpoints (missing geolocation)", className="mx-h1")

        if not filtered:
            return [header, html.Pre("(no unmapped public endpoints)")]

        def process_text(row: dict[str, Any]) -> tuple[str, str | None]:
            label = cls._safe_str(row.get("process_name"))
            if not label:
                label = cls._safe_str(row.get("process_status")) or "Unavailable"

            exe = row.get("exe")
            if isinstance(exe, str) and exe.strip():
                return label, exe.strip()

            status = row.get("process_status")
            if isinstance(status, str) and status.strip():
                return label, status.strip()

            return label, None

        def service_text(row: dict[str, Any]) -> tuple[str, str | None]:
            service = cls._safe_str(row.get("service")) or "Unknown"
            hint = cls._safe_str(row.get("service_hint")) or None
            return service, hint

        # 2) Aggregate identical endpoints and count sockets
        #    Key: (scope, ip, port, pid, process_label)
        agg: dict[tuple[str, str, int, int, str], dict[str, Any]] = {}
        for r in filtered:
            ip = cls._safe_str(r.get("ip"))
            port = cls._safe_int(r.get("port"), default=-1)
            scope = cls._remote_scope(ip)

            pid_val = r.get("pid")
            pid = cls._safe_int(pid_val) if pid_val is not None else -1

            proc_label, proc_tip = process_text(r)
            svc_val, svc_tip = service_text(r)

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
                # Keep a non-empty tooltip if one appears later
                if entry.get("process_tip") in {None, ""} and proc_tip:
                    entry["process_tip"] = proc_tip
                if entry.get("service_tip") in {None, ""} and svc_tip:
                    entry["service_tip"] = svc_tip

        aggregated = list(agg.values())

        # 3) Sort "signal first"
        interesting_ports = {443, 53, 80, 3478, 22, 3389}

        def sort_key(row: dict[str, Any]) -> tuple[int, int, int, str, str]:
            scope = cls._safe_str(row.get("scope"))
            port = cls._safe_int(row.get("port"), default=-1)
            proc = cls._safe_str(row.get("process"))
            ip = cls._safe_str(row.get("ip"))
            count = cls._safe_int(row.get("count"), default=0)

            port_rank = 0 if port in interesting_ports else 1
            # scope_rank: PUBLIC -> LAN -> LOCAL
            return (cls._scope_rank(scope), port_rank, -count, proc.lower(), ip)

        body_rows: list[Any] = []
        for row in sorted(aggregated, key=sort_key):
            scope = cls._safe_str(row.get("scope"))
            ip = cls._safe_str(row.get("ip"))
            port = cls._safe_int(row.get("port"), default=-1)

            service = cls._safe_str(row.get("service")) or "Unknown"
            service_tip = row.get("service_tip")
            service_tip = cls._safe_str(service_tip) or None

            pid_val = row.get("pid")
            pid_txt = str(cls._safe_int(pid_val)) if pid_val is not None else ""

            proc = cls._safe_str(row.get("process"))
            proc_tip = row.get("process_tip")
            proc_tip = cls._safe_str(proc_tip) or None

            count = cls._safe_int(row.get("count"), default=1)

            body_rows.append(
                html.Tr(
                    [
                        cls._cell(scope),
                        cls._cell(ip or "-"),
                        cls._cell(str(port) if port > 0 else "-"),
                        cls._cell(service, title=service_tip),
                        cls._cell(str(count)),
                        cls._cell(pid_txt),
                        cls._cell(proc, title=proc_tip),
                    ]
                )
            )

        colgroup = html.Colgroup(
            [
                html.Col(style={"width": "8%"}),   # Scope
                html.Col(style={"width": "28%"}),  # Remote IP
                html.Col(style={"width": "8%"}),   # Port
                html.Col(style={"width": "16%"}),  # Port service
                html.Col(style={"width": "8%"}),   # Count
                html.Col(style={"width": "8%"}),   # PID
                html.Col(style={"width": "24%"}),  # Process
            ]
        )

        table = html.Table(
            className="mx-table mx-unmapped",
            children=[
                colgroup,
                html.Thead(
                    html.Tr(
                        [
                            html.Th("Scope"),
                            html.Th("Remote IP"),
                            html.Th("Port"),
                            html.Th("Port service"),
                            html.Th("Count"),
                            html.Th("PID"),
                            html.Th("Process"),
                        ]
                    )
                ),
                html.Tbody(body_rows),
            ],
        )

        return [header, table]

    @classmethod
    def _render_lan_local(cls, snapshot: Any | None) -> list[Any]:
        """Render LAN and LOCAL established endpoints."""
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
            ip = r.get("ip")
            scope = cls._remote_scope(ip)
            if scope in {"LAN", "LOCAL"} and is_established_tcp(r):
                filtered.append(r)

        header = html.H1("Established LAN/LOCAL connections", className="mx-h1")

        if not filtered:
            return [header, html.Pre("(no LAN/LOCAL connections)")]

        def process_text(row: dict[str, Any]) -> tuple[str, str | None]:
            label = cls._safe_str(row.get("process_name"))
            if not label:
                label = cls._safe_str(row.get("process_status")) or "Unavailable"

            exe = row.get("exe")
            if isinstance(exe, str) and exe.strip():
                return label, exe.strip()

            status = row.get("process_status")
            if isinstance(status, str) and status.strip():
                return label, status.strip()

            return label, None

        def service_text(row: dict[str, Any]) -> tuple[str, str | None]:
            service = cls._safe_str(row.get("service")) or "Unknown"
            hint = cls._safe_str(row.get("service_hint")) or None
            return service, hint

        # Aggregate identical endpoints and count sockets
        # Key: (scope, ip, port, pid, process_label)
        agg: dict[tuple[str, str, int, int, str], dict[str, Any]] = {}
        for r in filtered:
            ip = cls._safe_str(r.get("ip"))
            port = cls._safe_int(r.get("port"), default=-1)
            scope = cls._remote_scope(ip)

            pid_val = r.get("pid")
            pid = cls._safe_int(pid_val) if pid_val is not None else -1

            proc_label, proc_tip = process_text(r)
            svc_val, svc_tip = service_text(r)

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

        aggregated = list(agg.values())

        interesting_ports = {443, 53, 80, 3478, 22, 3389}

        def sort_key(row: dict[str, Any]) -> tuple[int, int, int, str, str]:
            scope = cls._safe_str(row.get("scope"))
            port = cls._safe_int(row.get("port"), default=-1)
            proc = cls._safe_str(row.get("process"))
            ip = cls._safe_str(row.get("ip"))
            count = cls._safe_int(row.get("count"), default=0)

            port_rank = 0 if port in interesting_ports else 1
            return (cls._scope_rank(scope), port_rank, -count, proc.lower(), ip)

        body_rows: list[Any] = []
        for row in sorted(aggregated, key=sort_key):
            scope = cls._safe_str(row.get("scope"))
            ip = cls._safe_str(row.get("ip"))
            port = cls._safe_int(row.get("port"), default=-1)

            service = cls._safe_str(row.get("service")) or "Unknown"
            service_tip = cls._safe_str(row.get("service_tip")) or None

            pid_val = row.get("pid")
            pid_txt = str(cls._safe_int(pid_val)) if pid_val is not None else ""

            proc = cls._safe_str(row.get("process"))
            proc_tip = cls._safe_str(row.get("process_tip")) or None

            count = cls._safe_int(row.get("count"), default=1)

            body_rows.append(
                html.Tr(
                    [
                        cls._cell(scope),
                        cls._cell(ip or "-"),
                        cls._cell(str(port) if port > 0 else "-"),
                        cls._cell(service, title=service_tip),
                        cls._cell(str(count)),
                        cls._cell(pid_txt),
                        cls._cell(proc, title=proc_tip),
                    ]
                )
            )

        colgroup = html.Colgroup(
            [
                html.Col(style={"width": "8%"}),   # Scope
                html.Col(style={"width": "28%"}),  # Remote IP
                html.Col(style={"width": "8%"}),   # Port
                html.Col(style={"width": "16%"}),  # Port service
                html.Col(style={"width": "8%"}),   # Count
                html.Col(style={"width": "8%"}),   # PID
                html.Col(style={"width": "24%"}),  # Process
            ]
        )

        table = html.Table(
            className="mx-table mx-lan-local",
            children=[
                colgroup,
                html.Thead(
                    html.Tr(
                        [
                            html.Th("Scope"),
                            html.Th("Remote IP"),
                            html.Th("Port"),
                            html.Th("Port service"),
                            html.Th("Count"),
                            html.Th("PID"),
                            html.Th("Process"),
                        ]
                    )
                ),
                html.Tbody(body_rows),
            ],
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
        """Extract an endpoint index from Plotly customdata.

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