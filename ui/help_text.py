from dash import html

HELP_CONTENT = [
    html.H1("Help"),
    html.H2("Quick start"),
    html.P(
        "TapMap shows the remote systems your computer is connected to, "
        "their locations, and the local programs involved."
    ),
    html.Ul(
        [
            html.Li("Start TapMap."),
            html.Li(
                [
                    "If a 'Missing GeoIP databases' window appears:",
                    html.Ul(
                        [
                            html.Li("Click Open data folder."),
                            html.Li(
                                "Copy GeoLite2-City.mmdb and GeoLite2-ASN.mmdb into that folder."
                            ),
                            html.Li("Click Recheck GeoIP databases."),
                        ]
                    ),
                ]
            ),
            html.Li("Hover markers for a summary."),
            html.Li("Click markers for details."),
            html.Li("Use the mouse or Plotly tools (top right) to pan, zoom, or reset the view."),
        ]
    ),
    html.H2("Map legend"),
    html.Ul(
        [
            html.Li(
                [
                    html.Span("Magenta", style={"color": "magenta", "fontSize": "larger"}),
                    " markers and lines show normal remote connections.",
                ]
            ),
            html.Li(
                [
                    html.Span("Yellow", style={"color": "yellow", "fontSize": "larger"}),
                    " markers and lines indicate nearby locations.",
                ]
            ),
            html.Li(
                [
                    html.Span("Cyan", style={"color": "cyan", "fontSize": "larger"}),
                    " marker shows your location, if enabled.",
                ]
            ),
        ]
    ),
    html.P(
        "Yellow is a visual hint. Zoom in or change view direction to "
        "separate nearby endpoints."
    ),
    html.P(
        "Location grouping is a separate mechanism. Endpoints with the same rounded "
        "coordinates are shown as a single marker."
    ),
    html.H2("Controls"),
    html.Table(
        className="mx-table",
        style={"width": "auto"},
        children=[
            html.Thead(
                html.Tr(
                    [
                        html.Th("Key", style={"width": "50px"}),
                        html.Th("Action", style={"width": "350px"}),
                        html.Th("Result", style={"width": "75px"}),
                    ]
                )
            ),
            html.Tbody(
                [
                    html.Tr(
                        [
                            html.Td("U"),
                            html.Td("Show unmapped endpoints (missing geolocation)"),
                            html.Td("Window"),
                        ]
                    ),
                    html.Tr(
                        [
                            html.Td("O"),
                            html.Td("Show open ports (TCP LISTEN and UDP bound)"),
                            html.Td("Window"),
                        ]
                    ),
                    html.Tr([html.Td("T"), html.Td("Show cache in terminal"), html.Td("Status")]),
                    html.Tr([html.Td("C"), html.Td("Clear cache"), html.Td("Status")]),
                    html.Tr([html.Td("R"), html.Td("Recheck GeoIP databases"), html.Td("Status")]),
                    html.Tr([html.Td("H"), html.Td("Help"), html.Td("Window")]),
                    html.Tr([html.Td("A"), html.Td("About"), html.Td("Window")]),
                    html.Tr([html.Td("ESC"), html.Td("Close window"), html.Td("Window")]),
                ]
            ),
        ],
    ),
    html.H2("Unmapped endpoints"),
    html.P(
        "The Unmapped endpoints window lists ESTABLISHED TCP connections not shown on the "
        "map due to missing geolocation."
    ),
    html.P(
        "By default, only public endpoints are shown. Enable the toggle to include "
        "LAN and local endpoints."
    ),
    html.P(
        "In narrow windows, some fields may be truncated. Hover a cell to see the full value."
    ),
    html.H2("Open ports"),
    html.P(
        "The Open ports window lists local TCP sockets in LISTEN state and UDP sockets "
        "bound to local ports."
    ),
    html.P(
        "TCP LISTEN means a local process waits for incoming connections. "
        "UDP bound means a local process can receive datagrams on that port."
    ),
    html.P("This is a local view only. Remote endpoints are not shown."),
    html.H2("Show cache in terminal"),
    html.P("Print the current cache contents to the terminal where TapMap is running."),
    html.H2("Status line"),
    html.P("A snapshot is a view of network connections at a specific moment."),
    html.P(
        "Short status messages may appear after commands such as "
        "Clear cache, Show cache in terminal, or Recheck databases."
    ),
    html.H3("STATUS: WAIT | OK | OFFLINE | ERROR"),
    html.Ul(
        [
            html.Li("WAIT: No snapshot received yet."),
            html.Li("OK: Snapshot received successfully."),
            html.Li("OFFLINE: Snapshot received, but no internet connectivity detected."),
            html.Li("ERROR: Failed to fetch or enrich data. See terminal."),
        ]
    ),
    html.H3("LIVE"),
    html.P("Shows values from the current snapshot."),
    html.Ul(
        [
            html.Li("CON: Total TCP entries in all states."),
            html.Li("EST: Connections in state ESTABLISHED."),
            html.Li("LST: Listening TCP sockets on the local machine."),
        ]
    ),
    html.P("CON includes all TCP states, for example TIME_WAIT, SYN_SENT, and CLOSE_WAIT."),
    html.H3("CACHE"),
    html.P("Aggregated information since the last Clear cache or app start."),
    html.P("Only ESTABLISHED connections with a remote endpoint are included."),
    html.P("Format: EST - LOC - NON_GEO = GEO -> RIP -> RLOC"),
    html.Ul(
        [
            html.Li(
                "EST: Unique remote endpoints seen in ESTABLISHED connections, "
                "defined as remote IP and port."
            ),
            html.Li(
                "LOC: Endpoints where the remote IP is local, private, or loopback. "
                "Not shown on the map."
            ),
            html.Li(
                "NON_GEO: External endpoints without geolocation. "
                "Not shown on the map but available via key U."
            ),
            html.Li("GEO: External endpoints with valid geolocation. GEO = EST - LOC - NON_GEO."),
            html.Li("RIP: Unique remote IP addresses within GEO."),
            html.Li(
                "RLOC: Map locations within GEO after coordinate grouping. "
                "Multiple IPs and ASNs may map to the same grouped location."
            ),
        ]
    ),
    html.H3("UPDATED"),
    html.P("Time of the last snapshot."),
    html.H3("MYLOC: FIXED | AUTO | AUTO (NO GEO) | OFF"),
    html.P("Shows your local map location based on the MY_LOCATION setting in config.py."),
    html.Ul(
        [
            html.Li("FIXED: Uses fixed coordinates from config.py."),
            html.Li("AUTO: Location detected from your public IP."),
            html.Li("AUTO (NO GEO): Public IP detected, but no geolocation available."),
            html.Li("OFF: Local marker and connection lines are hidden."),
        ]
    ),
    html.H2("GeoIP databases (MaxMind GeoLite2)"),
    html.P("TapMap uses local MaxMind mmdb files for geolocation. The databases are not included."),
    html.P("Required files:"),
    html.Ul(
        [
            html.Li("GeoLite2-City.mmdb"),
            html.Li("GeoLite2-ASN.mmdb"),
        ]
    ),
    html.P("If the databases are missing, a setup window appears at startup."),
    html.P(
        "Open the data folder from that window or from About. Copy the files into it and use "
        "Recheck GeoIP databases to enable geolocation without restarting."
    ),
    html.P(
        [
            "The databases are free from MaxMind but require an account and "
            "acceptance of license terms. ",
            "Download them here: ",
            html.A(
                "MaxMind GeoLite2 download page",
                href="https://dev.maxmind.com/geoip/geolite2-free-geolocation-data",
                target="_blank",
            ),
            ".",
        ]
    ),
    html.P("Update the databases regularly, for example monthly."),
    html.H2("Configuration (config.py)"),
    html.P("TapMap reads settings from config.py. Edit this file to adjust behavior."),
    html.P("Common settings:"),
    html.Ul(
        [
            html.Li(
                "MY_LOCATION: 'none' hides the local marker. Use (lon, lat) for fixed "
                "coordinates, or 'auto' to detect from public IP."
            ),
            html.Li("POLL_INTERVAL_MS: Snapshot refresh interval in milliseconds."),
            html.Li(
                "COORD_PRECISION: Decimal precision used to group endpoints into one marker. "
                "3 is approximately 100 meters."
            ),
            html.Li("ZOOM_NEAR_KM: Distance threshold for marking endpoints as nearby in yellow."),
        ]
    ),
    html.H2("Network and location notes"),
    html.Ul(
        [
            html.Li("IP-based geolocation is approximate."),
            html.Li(
                "ASN and ASN organization identify the network operator, not "
                "necessarily the service owner."
            ),
            html.Li("CDNs and hosting providers can make a service appear in another country."),
            html.Li("VPN and Tor can hide the true origin of a remote endpoint."),
        ]
    ),
    html.H2("Privacy and safety"),
    html.P("TapMap runs locally and reads local network connections."),
    html.P("Geolocation lookups are performed locally using the mmdb files."),
    html.P(
        "If MY_LOCATION is set to 'auto', TapMap may query external services "
        "to detect the public IP address. It stops after the first valid result."
    ),
    html.P(
        "To detect OFFLINE status, TapMap performs short connection checks to 1.1.1.1 and 8.8.8.8."
    ),
]