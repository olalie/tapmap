"""Help view rendering for the TapMap UI.

Build the Help modal content shown in the application.
Contain no application state logic.
"""

from __future__ import annotations

from typing import Any

from dash import html


def render_help() -> list[Any]:
    """Build Help modal content.

    Returns a list of Dash components representing the Help window.
    No side effects. Pure view construction.
    """
    return [
        html.H1("Help"),
        html.P(
            [
                "TapMap shows where your computer connects on a world map.",
                html.Br(),
                "Explore each location for summaries and details about the systems and the local ",
                "apps involved.",
            ]
        ),
        html.H2("Quick start"),
        html.Ul(
            [
                html.Li("Start TapMap."),
                html.Li("Hover map markers for a connection summary."),
                html.Li(
                    "Click map markers for connection details and application information."
                ),
                html.Li(
                    "The Insights panel highlights new and frequent activity."
                ),
                html.Li(
                    "Open the Daily Activity Report (D) for deeper analysis of activity patterns."
                ),
                html.Li(
                    "Use the menu to explore unmapped services, LAN/LOCAL services, "
                    "open ports, and additional tools."
                ),
                html.Li(
                    "Use the mouse or Plotly tools (top right) to pan, zoom, reset, or fit all "
                    "mapped connections."
                ),
            ]
        ),
        html.H2("Definitions"),
        html.P(
            "The map shows connections observed since TapMap started or Clear cache "
            "(C) was last used."
        ),
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
                                        html.Br(),
                                        "Hover for a summary or click for connection and "
                                        "application information.",
                                    ]
                                ),
                            ]
                        ),
                    ]
                ),
            ],
        ),
        html.P(
            [
                "Scope describes where an address belongs:",
                html.Br(),
                "external internet (PUBLIC), your local network (LAN), or your own "
                "machine (LOCAL).",
            ]
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
                "Location grouping is separate. PUBLIC services with the same rounded "
                "coordinates are shown as one marker.",
            ]
        ),
        html.H2("Menu"),
        html.P(
            "The menu is organized into the expandable sections INSIGHTS, NETWORK, "
            "TOOLS, and INFO."
        ),
        html.Table(
            className="mx-table mx-kv",
            children=[
                html.Tbody(
                    [
                        html.Tr(
                            [
                                html.Td("INSIGHTS"),
                                html.Td(
                                    "Daily Activity Report, Insights panel, and "
                                    "Significant Connections."
                                ),
                            ]
                        ),
                        html.Tr(
                            [
                                html.Td("NETWORK"),
                                html.Td(
                                    "Unmapped public services, LAN/LOCAL services, open ports, "
                                    "and the Technical details option."
                                ),
                            ]
                        ),
                        html.Tr(
                            [
                                html.Td("TOOLS"),
                                html.Td(
                                    "GeoIP Database Management, cache actions, and "
                                    "Run TapMap automatically."
                                ),
                            ]
                        ),
                        html.Tr(
                            [
                                html.Td("INFO"),
                                html.Td(
                                    "Help and About windows."
                                ),
                            ]
                        ),
                    ]
                ),
            ],
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
                                html.Td("D"),
                                html.Td("Show Daily Activity Report"),
                                html.Td("Window"),
                            ]
                        ),
                        html.Tr(
                            [
                                html.Td("I"),
                                html.Td("Toggle Insights panel"),
                                html.Td("Panel"),
                            ]
                        ),
                        html.Tr(
                            [
                                html.Td("S"),
                                html.Td("Show Significant Connections history"),
                                html.Td("Window"),
                            ]
                        ),
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
                        html.Tr(
                            [
                                html.Td("T"),
                                html.Td("Toggle Technical details"),
                                html.Td("Option"),
                            ]
                        ),
                        html.Tr(
                            [
                                html.Td("G"),
                                html.Td("Open GeoIP Database Management"),
                                html.Td("Window"),
                            ]
                        ),
                        html.Tr(
                            [
                                html.Td("R"),
                                html.Td("Toggle Run TapMap automatically"),
                                html.Td("Option"),
                            ]
                        ),
                        html.Tr([html.Td("E"), html.Td("Export cache"), html.Td("Download")]),
                        html.Tr([html.Td("C"), html.Td("Clear cache"), html.Td("Status")]),
                        html.Tr([html.Td("H"), html.Td("Help"), html.Td("Window")]),
                        html.Tr([html.Td("A"), html.Td("About"), html.Td("Window")]),
                        html.Tr([html.Td("Z"), html.Td("Fit mapped connections"),
                                 html.Td("Map")]),
                        html.Tr([html.Td("X"), html.Td("Exit"), html.Td("Exit")]),
                        html.Tr([html.Td("ESC"), html.Td("Close window"), html.Td("Window")]),
                    ]
                ),
            ],
        ),
        html.H2("System tray and autostart"),
        html.P(
            [
                "Closing the browser tab or window does not stop TapMap.",
                html.Br(),
                "Use the system tray icon (menu bar on macOS) to reopen TapMap in the browser, "
                "or to quit it. Exit (X) also stops TapMap.",
            ]
        ),
        html.P(
            [
                html.B("Run TapMap automatically"),
                " starts TapMap at login without opening the browser. Change it from the TOOLS "
                "menu or press R.",
            ]
        ),
        html.P(
            "The system tray and autostart are available for desktop installations, not "
            "Docker."
        ),
        html.H2("Application information"),
        html.P(
            [
                "Hover over a map marker to see a summary of the applications using "
                "the selected network operator.",
                html.Br(),
                "Click a map marker for more details.",
            ]
        ),
        html.P(
            [
                "Enable ",
                html.B("Technical details"),
                " in the NETWORK section of the menu to display executable paths, "
                "processes, PIDs, signatures, and other technical information.",
            ]
        ),
        html.P(
            "TapMap identifies the process handling each connection. If an application uses "
            "a separate helper, runtime, or interpreter, TapMap may identify that process "
            "rather than the application that launched it."
        ),
        html.H3("Application verification"),
        html.Table(
            className="mx-table mx-kv",
            children=[
                html.Tbody(
                    [
                        html.Tr(
                            [
                                html.Td(
                                    html.Span("■", style={"color": "#00ff66"})
                                ),
                                html.Td("Verified: Verification succeeded."),
                            ]
                        ),
                        html.Tr(
                            [
                                html.Td(
                                    html.Span("■", style={"color": "#ff4444"})
                                ),
                                html.Td("Failed: Verification failed."),
                            ]
                        ),
                        html.Tr(
                            [
                                html.Td(
                                    html.Span("■", style={"color": "#ffff00"})
                                ),
                                html.Td(
                                    "Unknown or unavailable: Verification could not be completed."
                                ),
                            ]
                        ),
                        html.Tr(
                            [
                                html.Td(
                                    html.Span("■", style={"color": "#ffffff"})
                                ),
                                html.Td(
                                    "Retrieving...: Verification is in progress."
                                ),
                            ]
                        ),
                    ]
                ),
            ],
        ),
        html.H2("Map navigation"),
        html.P(
            [
                "Hover a map marker for a connection summary.",
                html.Br(),
                "Click a map marker for connection details and application information.",
                html.Br(),
                "Use the Fit Connections button in the Plotly toolbar (top right), or "
                "press Z, to fit all mapped connections.",
                html.Br(),
                "Click a country in the Insights panel to zoom to that country.",
            ]
        ),
        html.H2("Insights"),
        html.P(
            "The Insights panel highlights mapped public activity observed during "
            "the last 30 days."
        ),
        html.Ul(
            [
                html.Li(
                    "New apps, providers (ASN), countries, and ports observed today."
                ),
                html.Li(
                    "Top 5+ most frequently observed items over the last 30 days."
                ),
                html.Li(
                    "Click countries to zoom to the selected country."
                ),
            ]
        ),
        html.P(
            "Insights may include mapped activity that is no longer visible on the map because "
            "the map covers the current session, while Insights retain activity for 30 days."
        ),
        html.H2("Daily Activity Report"),
        html.P(
            "The Daily Activity Report analyzes mapped public activity observed "
            "during the last 30 days."
        ),
        html.Ul(
            [
                html.Li(
                    "Application recurrence patterns (seen once, occasional, "
                    "recurring, and stable)."
                ),
                html.Li("Provider concentration analysis."),
                html.Li("Country activity visualization."),
                html.Li(
                    "Open the generated activity log from the Log section at the "
                    "end of the report to inspect detailed timelines for apps, "
                    "providers, countries, and ports."
                ),
            ]
        ),
        html.P(
            "To build a complete 30-day history, keep TapMap running while your system is in "
            "use. Enable Run TapMap automatically (R) to start TapMap at login."
        ),
        html.H2("Significant Connections"),
        html.P(
            "Significant Connections lists connection events flagged for a new "
            "application, country, network operator, port, or failed verification."
        ),
        html.P(
            "Click a row to view location, application, connection, and process "
            "details. Use Back to return to the list."
        ),
        html.P(
            "Missing historical verification status is shown as Unknown."
        ),
        html.P("TapMap keeps the most recent 500 Significant Connections."),
        html.H2("Unmapped public services (missing geolocation)"),
        html.P(
            "The Unmapped window lists PUBLIC services that are not shown on the map because "
            "geolocation is missing."
        ),
        html.P(
            "Scope in this window describes where the service address belongs. "
            "LAN and LOCAL services are excluded from this view."
        ),
        html.P(
            "Count shows how many sockets were merged into the row for the latest snapshot. "
            "Rows are grouped by scope, protocol, IP, port, PID, and process."
        ),
        html.P(
            "In narrow windows, some fields may be truncated. Hover a cell to see the full value."
        ),
        html.H2("Established LAN/LOCAL services"),
        html.P(
            "This window lists established TCP sockets where the service is LAN or LOCAL. "
            "These services are not shown on the map."
        ),
        html.P(
            "Count shows how many sockets were merged into the row for the latest snapshot. "
            "Rows are grouped by scope, protocol, IP, port, PID, and process for the other side."
        ),
        html.P("Scope in this window describes where the service address belongs."),
        html.H2("Open ports (TCP LISTEN and UDP bound)"),
        html.P(
            [
                "The Open ports window lists local TCP sockets in LISTEN state and UDP sockets "
                "bound to local ports."
            ]
        ),
        html.P(
            "TCP LISTEN means a local process waits for incoming connections. "
            "UDP bound means a local process can receive datagrams on that port."
        ),
        html.P("This is a local view only. Services on the other side are not shown."),
        html.P(
            "Scope in this window describes how the local process is bound: "
            "loopback only, LAN only, or all interfaces."
        ),
        html.P("System processes are hidden by default. Use the toggle to include them."),
        html.H2("Status line"),
        html.P(
            "Short status messages may appear after commands such as Clear cache."
        ),
        html.H3("STATUS: WAIT | OK | ERROR"),
        html.Table(
            className="mx-table mx-kv",
            children=[
                html.Tbody(
                    [
                        html.Tr([html.Td("WAIT"), html.Td("No snapshot received yet.")]),
                        html.Tr([html.Td("OK"), html.Td("Snapshot received without errors.")]),
                        html.Tr(
                            [
                                html.Td("ERROR"),
                                html.Td("Failed to fetch or enrich data. See terminal."),
                            ]
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
                                html.Td(
                                    "Total TCP entries in the snapshot, across all TCP states."
                                ),
                            ]
                        ),
                        html.Tr([html.Td("EST"), html.Td("TCP entries in state ESTABLISHED.")]),
                        html.Tr(
                            [
                                html.Td("LST"),
                                html.Td("Listening TCP sockets on the local machine."),
                            ]
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
        html.P(
            [
                "CACHE shows aggregated counters since the last Clear cache or app start.",
                html.Br(),
                "The map view is based on this cached data.",
            ]
        ),
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
        html.H3("MYLOC: FIXED | ENV | AUTO | AUTO (NO GEO) | OFF"),
        html.P("Shows the active local map location mode."),
        html.Table(
            className="mx-table mx-kv",
            children=[
                html.Tbody(
                    [
                        html.Tr(
                            [html.Td("FIXED"), html.Td("Uses fixed coordinates from config.py.")]
                        ),
                        html.Tr(
                            [
                                html.Td("ENV"),
                                html.Td(
                                    "Uses coordinates provided through TAPMAP_LON and TAPMAP_LAT."
                                ),
                            ]
                        ),
                        html.Tr(
                            [html.Td("AUTO"), html.Td("Location detected from your public IP.")]
                        ),
                        html.Tr(
                            [
                                html.Td("AUTO (NO GEO)"),
                                html.Td("Public IP detected, but no geolocation available."),
                            ]
                        ),
                        html.Tr(
                            [
                                html.Td("OFF"),
                                html.Td("Local marker and connection lines are hidden."),
                            ]
                        ),
                    ]
                ),
            ],
        ),
        html.H2("GeoIP databases"),
        html.P(
            "TapMap uses local GeoIP databases for geolocation. Supported providers "
            "include MaxMind GeoLite2 and DB-IP Lite."
        ),
        html.P(
            "GeoIP Database Management is used to install, update, verify, and manage "
            "supported databases."
        ),
            html.P(
                "When no supported databases are detected, GeoIP Database Management "
                "provides installation options for supported providers."
            ),
        html.P(
            "Databases can be installed from GeoIP Database Management or managed "
            "manually using the data folder."
        ),
        html.P(
            "Keep the databases up to date. Use the Update databases button regularly, "
            "for example once a month."
        ),
        html.H2("Network and location notes"),
        html.P(
            "Locations are based on IP geolocation data and are approximate. TapMap does not "
            "independently determine or verify the physical location of the network endpoint."
        ),
        html.P(
            "ASN and ASN organization identify the network operator, not necessarily the "
            "service owner."
        ),
        html.P(
            "For some network infrastructure, including anycast services, CDNs, proxies, and "
            "VPNs, the displayed location may differ from the physical location of the "
            "endpoint handling the connection."
        ),
        html.H2("Privacy"),
        html.Ul(
            [
                html.Li("TapMap runs locally."),
                html.Li("No connection data is sent anywhere."),
                html.Li("Geolocation uses local GeoIP databases."),
                html.Li(
                    "TapMap stores activity history and significant connection events locally. "
                    "This data is never transmitted or shared by TapMap."
                ),
                html.Li(
                    "If automatic local geolocation is enabled, TapMap contacts a public "
                    "IP lookup service to determine your public IP address."
                ),
                html.Li(
                    "External public-IP lookup can be avoided by using fixed local coordinates."
                ),
                html.Li(
                    "GeoIP databases can be installed and updated from within TapMap or "
                    "managed manually."
                ),
            ]
        ),
    ]
