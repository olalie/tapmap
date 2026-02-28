from dash import html

HELP_CONTENT = [
    html.H1("Help"),
    html.P(
        [
            "TapMap shows the locations of the systems your computer connects to on a world map.",
            html.Br(),
            "Explore each location for summaries and details about the systems and the local ",
            "programs involved.",
        ]
    ),
    html.H2("Quick start"),
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
            html.Li("Hover map markers for a summary."),
            html.Li("Click map markers for detailed information."),
            html.Li("Use the mouse or Plotly tools (top right) to pan, zoom, or reset the view."),
        ]
    ),
    html.H2("Definitions"),
    html.Table(
        className="mx-table mx-kv",
        children=[
            html.Tbody(
                [
                    html.Tr(
                        [
                            html.Td("Snapshot"),
                            html.Td(
                                "A readout of network connections at a specific moment "
                                "(refreshed regularly)."
                            ),
                        ]
                    ),
                    html.Tr(
                        [
                            html.Td("Service"),
                            html.Td(
                                "A service on the other side, identified by protocol, IP, and "
                                "port."
                            ),
                        ]
                    ),
                    html.Tr(
                        [
                            html.Td("Socket"),
                            html.Td(
                                [
                                    "One local process using one socket entry in the snapshot.",
                                    html.Br(),
                                    "Multiple sockets can refer to the same service.",
                                ]
                            ),
                        ]
                    ),
                    html.Tr(
                        [
                            html.Td("Map marker"),
                            html.Td(
                                [
                                    "A location on the map.",
                                    html.Br(),
                                    "One marker can represent multiple services "
                                    "if they share the same rounded coordinates.",
                                ]
                            ),
                        ]
                    ),
                ]
            ),
        ],
    ),
    html.H3("Scope"),
    html.Table(
        className="mx-table mx-kv",
        children=[
            html.Tbody(
                [
                    html.Tr([html.Td("PUBLIC"), html.Td("External internet address.")]),
                    html.Tr(
                        [
                            html.Td("LAN"),
                            html.Td(
                                "Private network address, for example 192.168.x.x or 10.x.x.x."
                            ),
                        ]
                    ),
                    html.Tr(
                        [
                            html.Td("LOCAL"),
                            html.Td("Loopback address, for example 127.0.0.1 or ::1."),
                        ]
                    ),
                ]
            ),
        ],
    ),
    html.P(
        "Map markers represent PUBLIC services with geolocation. "
        "LAN and LOCAL services are not shown on the map."
    ),
    html.H2("Map legend"),
    html.Ul(
        [
            html.Li(
                [
                    html.Span("Magenta", style={"color": "magenta", "fontSize": "larger"}),
                    " markers and lines show PUBLIC services with geolocation.",
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
        [
            "Yellow is a visual hint. Zoom in or change view direction to separate "
            "nearby locations.",
            html.Br(),
            "Location grouping is separate. PUBLIC services with the same rounded coordinates are "
            "shown as one marker.",
        ]
    ),
    html.H2("Controls"),
    html.Table(
        className="mx-table",
        children=[
            html.Colgroup(
                [
                    html.Col(style={"width": "50px"}),
                    html.Col(),
                    html.Col(style={"width": "75px"}),
                ]
            ),
            html.Thead(
                html.Tr(
                    [
                        html.Th("Key"),
                        html.Th("Action"),
                        html.Th("Result"),
                    ]
                )
            ),
            html.Tbody(
                [
                    html.Tr(
                        [
                            html.Td("U"),
                            html.Td("Show unmapped public services (missing geolocation)"),
                            html.Td("Window"),
                        ]
                    ),
                    html.Tr(
                        [
                            html.Td("L"),
                            html.Td("Show established LAN and LOCAL services"),
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
    html.H2("Unmapped public services"),
    html.P(
        "The Unmapped window lists PUBLIC services that are not shown on the map because "
        "geolocation is missing."
    ),
    html.P("LAN and LOCAL services are excluded from this view."),
    html.P(
        "Count shows how many sockets were merged into the row for the latest snapshot. "
        "Rows are grouped by scope, protocol, IP, port, PID, and process for the other side."
    ),
    html.P("In narrow windows, some fields may be truncated. Hover a cell to see the full value."),
    html.H2("Established LAN/LOCAL services"),
    html.P(
        "This window lists established TCP sockets where the service is LAN or LOCAL. "
        "These services are not shown on the map."
    ),
    html.P(
        "Count shows how many sockets were merged into the row for the latest snapshot. "
        "Rows are grouped by scope, protocol, IP, port, PID, and process for the other side."
    ),
    html.H2("Open ports"),
    html.P(
        "The Open ports window lists local TCP sockets in LISTEN state and UDP sockets bound to "
        "local ports."
    ),
    html.P(
        "TCP LISTEN means a local process waits for incoming connections. "
        "UDP bound means a local process can receive datagrams on that port."
    ),
    html.P("This is a local view only. Services on the other side are not shown."),
    html.P("System processes are hidden by default. Use the toggle to include them."),
    html.H2("Show cache in terminal"),
    html.P("Print the current cache contents to the terminal where TapMap is running."),
    html.H2("Status line"),
    html.P(
        "Short status messages may appear after commands such as Clear cache or Recheck databases."
    ),
    html.H3("STATUS: WAIT | OK | OFFLINE | ERROR"),
    html.Table(
        className="mx-table mx-kv",
        children=[
            html.Tbody(
                [
                    html.Tr([html.Td("WAIT"), html.Td("No snapshot received yet.")]),
                    html.Tr([html.Td("OK"), html.Td("Snapshot received successfully.")]),
                    html.Tr(
                        [
                            html.Td("OFFLINE"),
                            html.Td("Snapshot received, but no internet connectivity detected."),
                        ]
                    ),
                    html.Tr(
                        [html.Td("ERROR"), html.Td("Failed to fetch or enrich data. See terminal.")]
                    ),
                ]
            ),
        ],
    ),
    html.H3("LIVE"),
    html.P("LIVE shows counters from the current snapshot."),
    html.Table(
        className="mx-table mx-kv",
        children=[
            html.Tbody(
                [
                    html.Tr(
                        [
                            html.Td("TCP"),
                            html.Td("Total TCP entries in the snapshot, across all TCP states."),
                        ]
                    ),
                    html.Tr([html.Td("EST"), html.Td("TCP entries in state ESTABLISHED.")]),
                    html.Tr(
                        [html.Td("LST"), html.Td("Listening TCP sockets on the local machine.")]
                    ),
                    html.Tr(
                        [
                            html.Td("UDP R"),
                            html.Td("UDP entries that have a remote address available."),
                        ]
                    ),
                    html.Tr([html.Td("UDP B"), html.Td("UDP entries bound to a local port.")]),
                ]
            ),
        ],
    ),
    html.P("TCP includes states such as TIME_WAIT, SYN_SENT, and CLOSE_WAIT."),
    html.H3("CACHE"),
    html.P("CACHE shows aggregated counters since the last Clear cache or app start."),
    html.Table(
        className="mx-table mx-kv",
        children=[
            html.Tbody(
                [
                    html.Tr(
                        [
                            html.Td("SOCK"),
                            html.Td("Unique sockets (proto, IP, port, PID or process)."),
                        ]
                    ),
                    html.Tr(
                        [
                            html.Td("SERV"),
                            html.Td("Unique services (proto, IP, port)."),
                        ]
                    ),
                    html.Tr(
                        [
                            html.Td("MAP"),
                            html.Td("Unique mapped public services (have geolocation)."),
                        ]
                    ),
                    html.Tr(
                        [
                            html.Td("UNM"),
                            html.Td("Unique unmapped public services (missing geolocation)."),
                        ]
                    ),
                    html.Tr([html.Td("LOC"), html.Td("Unique LAN and loopback services.")]),
                ]
            ),
        ],
    ),
    html.P("SERV is derived from SOCK by ignoring PID and process."),
    html.H3("UPDATED"),
    html.P("Time of the last snapshot."),
    html.H3("MYLOC: FIXED | AUTO | AUTO (NO GEO) | OFF"),
    html.P("Shows your local map location based on the MY_LOCATION setting in config.py."),
    html.Table(
        className="mx-table mx-kv",
        children=[
            html.Tbody(
                [
                    html.Tr([html.Td("FIXED"), html.Td("Uses fixed coordinates from config.py.")]),
                    html.Tr([html.Td("AUTO"), html.Td("Location detected from your public IP.")]),
                    html.Tr(
                        [
                            html.Td("AUTO (NO GEO)"),
                            html.Td("Public IP detected, but no geolocation available."),
                        ]
                    ),
                    html.Tr(
                        [html.Td("OFF"), html.Td("Local marker and connection lines are hidden.")]
                    ),
                ]
            ),
        ],
    ),
    html.H2("GeoIP databases (MaxMind GeoLite2)"),
    html.P("TapMap uses local MaxMind mmdb files for geolocation. The databases are not included."),
    html.P("Required files:"),
    html.Ul([html.Li("GeoLite2-City.mmdb"), html.Li("GeoLite2-ASN.mmdb")]),
    html.P("If the databases are missing, a setup window appears at startup."),
    html.P(
        "Open the data folder from that window or from About. Copy the files into it and use "
        "Recheck GeoIP databases to enable geolocation without restarting."
    ),
    html.P(
        [
            "The databases are free from MaxMind but require an account and acceptance of license "
            "terms. Download them here: ",
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
    html.Table(
        className="mx-table mx-kv",
        children=[
            html.Colgroup([html.Col(style={"width": "130px"}), html.Col()]),
            html.Tbody(
                [
                    html.Tr(
                        [
                            html.Td("MY_LOCATION"),
                            html.Td(
                                "'none' hides the local marker. Use (lon, lat) for fixed "
                                "coordinates, or 'auto' to detect from public IP."
                            ),
                        ]
                    ),
                    html.Tr(
                        [
                            html.Td("POLL_INTERVAL_MS"),
                            html.Td("Snapshot refresh interval in milliseconds."),
                        ]
                    ),
                    html.Tr(
                        [
                            html.Td("COORD_PRECISION"),
                            html.Td(
                                "Decimal precision used to group PUBLIC services into one marker. "
                                "3 is approximately 100 meters."
                            ),
                        ]
                    ),
                    html.Tr(
                        [
                            html.Td("ZOOM_NEAR_KM"),
                            html.Td(
                                "Distance threshold for marking locations as nearby in yellow."
                            ),
                        ]
                    ),
                ]
            ),
        ],
    ),
    html.H2("Network and location notes"),
    html.P("IP based geolocation is approximate."),
    html.P(
        "ASN and ASN organization identify the network operator, not necessarily the service owner."
    ),
    html.P("CDNs and hosting providers can make a service appear in another country."),
    html.P("VPN and Tor can hide the true origin of a PUBLIC service location."),
    html.H2("Privacy and safety"),
    html.P("TapMap runs locally and reads local network connections."),
    html.P("Geolocation lookups are performed locally using the mmdb files."),
    html.P(
        "If MY_LOCATION is set to 'auto', TapMap may query external services to detect the public "
        "IP address. It stops after the first valid result."
    ),
    html.P(
        "To detect OFFLINE status, TapMap performs short connection checks to 1.1.1.1 and 8.8.8.8."
    ),
]
