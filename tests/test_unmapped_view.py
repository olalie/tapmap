"""Test unmapped_view's technical and application-oriented presentations."""

from __future__ import annotations

from typing import Any

from dash import html

from tapmap.state.unmapped_state import UnmappedState
from tapmap.ui.unmapped_view import render_unmapped


def _entry(
    *,
    ip: str = "203.0.113.7",
    port: int = 8443,
    service: str = "https",
    applications: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a minimal UnmappedState-shaped cache entry."""
    return {
        "ip": ip,
        "port": port,
        "proto": "tcp",
        "service": service,
        "applications": applications if applications is not None else {},
    }


def _app(
    *,
    app_name: str | None = None,
    app_creator: str | None = None,
    app_verification_status: str | None = None,
    exe: str | None = "/opt/app.exe",
    processes: list[str] | None = None,
    proc_pids: dict[str, list[int]] | None = None,
) -> dict[str, Any]:
    """Return a minimal application record for one entry's applications dict."""
    return {
        "app_name": app_name,
        "app_creator": app_creator,
        "app_verification_status": app_verification_status,
        "app_signature_state": None,
        "app_signature_state_details": None,
        "exe": exe,
        "processes": processes if processes is not None else [],
        "proc_pids": proc_pids if proc_pids is not None else {},
    }


def _table_rows(component: html.Table) -> list[html.Tr]:
    """Return the body rows from a rendered table component."""
    tbody = next(c for c in component.children if isinstance(c, html.Tbody))
    return tbody.children


def _cell_text(td: html.Td) -> str:
    """Return the visible text of one rendered table cell."""
    return td.children.children


# --- empty state ---


def test_render_unmapped_empty_cache_shows_placeholder() -> None:
    """An empty UnmappedState renders a placeholder, not a table, in either mode."""
    result = render_unmapped({}, technical_details_enabled=True)

    assert isinstance(result[1], html.Pre)
    assert "no unmapped" in result[1].children.lower()


# --- technical details ON ---


def test_technical_table_has_no_count_column() -> None:
    """The technical table's headers do not include Count."""
    cache = {"203.0.113.7|8443": _entry(applications={"/opt/app.exe": _app(app_name="Firefox")})}

    result = render_unmapped(cache, technical_details_enabled=True)
    table = result[1]

    thead = next(c for c in table.children if isinstance(c, html.Thead))
    headers = [th.children for th in thead.children.children]

    assert headers == ["Scope", "Remote IP", "Port", "Port service", "PID", "Process"]


def test_technical_row_shows_service_identity_and_joined_pids() -> None:
    """A technical row shows Scope/IP/Port/Port service, plus every distinct PID joined."""
    cache = {
        "203.0.113.7|8443": _entry(
            ip="203.0.113.7",
            port=8443,
            service="https",
            applications={
                "/opt/firefox.exe": _app(
                    app_name="Firefox",
                    processes=["firefox.exe"],
                    proc_pids={"firefox.exe": [4821, 5190]},
                )
            },
        )
    }

    result = render_unmapped(cache, technical_details_enabled=True)
    rows = _table_rows(result[1])
    cells = [_cell_text(td) for td in rows[0].children]

    assert cells == ["PUBLIC", "203.0.113.7", "8443", "https", "4821, 5190", "firefox.exe"]


def test_technical_view_gives_each_application_at_a_service_its_own_row() -> None:
    """Two different applications sharing (ip, port) each get their own technical row."""
    cache = {
        "203.0.113.7|8443": _entry(
            applications={
                "/opt/firefox.exe": _app(app_name="Firefox"),
                "/tmp/malware.exe": _app(app_name="Malware"),
            }
        )
    }

    result = render_unmapped(cache, technical_details_enabled=True)
    rows = _table_rows(result[1])

    assert len(rows) == 2


def test_technical_view_shows_multiple_services() -> None:
    """Each distinct service entry contributes its own row(s)."""
    cache = {
        "203.0.113.7|8443": _entry(
            ip="203.0.113.7", port=8443, applications={"/a.exe": _app(app_name="App A")}
        ),
        "198.51.100.4|443": _entry(
            ip="198.51.100.4", port=443, applications={"/b.exe": _app(app_name="App B")}
        ),
    }

    result = render_unmapped(cache, technical_details_enabled=True)
    rows = _table_rows(result[1])

    assert len(rows) == 2


def test_technical_view_shows_unknown_bucket_process_without_app_name() -> None:
    """An application with no resolvable exe still shows its process name in the technical view."""
    cache = {
        "203.0.113.7|8443": _entry(
            applications={
                "__unknown_application__": _app(
                    app_name=None,
                    exe=None,
                    processes=["svchost.exe"],
                    proc_pids={"svchost.exe": [100]},
                )
            }
        )
    }

    result = render_unmapped(cache, technical_details_enabled=True)
    rows = _table_rows(result[1])
    cells = [_cell_text(td) for td in rows[0].children]

    assert cells[5] == "svchost.exe"
    assert cells[4] == "100"


# --- technical details OFF ---


def test_general_table_has_expected_columns() -> None:
    """The application-oriented table has the Application/Creator/Verification/Services headers."""
    cache = {"203.0.113.7|8443": _entry(applications={"/a.exe": _app(app_name="Firefox")})}

    result = render_unmapped(cache, technical_details_enabled=False)
    table = result[1]
    thead = next(c for c in table.children if isinstance(c, html.Thead))
    headers = [th.children for th in thead.children.children]

    assert headers == ["Application", "Creator", "Verification", "Services"]


def test_general_view_services_counts_distinct_ip_port_entries() -> None:
    """Services is the number of distinct ip|port entries observed for that application."""
    cache = {
        "203.0.113.7|8443": _entry(
            ip="203.0.113.7",
            port=8443,
            applications={
                "/firefox.exe": _app(
                    app_name="Firefox",
                    app_creator="Mozilla",
                    app_verification_status="verified",
                )
            },
        ),
        "198.51.100.4|443": _entry(
            ip="198.51.100.4",
            port=443,
            applications={
                "/firefox.exe": _app(
                    app_name="Firefox",
                    app_creator="Mozilla",
                    app_verification_status="verified",
                )
            },
        ),
    }

    result = render_unmapped(cache, technical_details_enabled=False)
    rows = _table_rows(result[1])
    cells = [_cell_text(td) for td in rows[0].children]

    assert cells[0] == "Firefox"
    assert cells[1] == "Mozilla"
    assert cells[3] == "2"


def test_general_view_groups_different_exe_paths_sharing_app_name_into_one_row() -> None:
    """Different exe paths that report the same app_name collapse into one application row."""
    cache = {
        "1.1.1.1|443": _entry(
            ip="1.1.1.1",
            port=443,
            applications={
                "/OneDrive.exe": _app(app_name="Microsoft OneDrive", app_creator="Microsoft"),
            },
        ),
        "2.2.2.2|443": _entry(
            ip="2.2.2.2",
            port=443,
            applications={
                "/FileSyncHelper.exe": _app(
                    app_name="Microsoft OneDrive", app_creator="Microsoft"
                ),
            },
        ),
    }

    result = render_unmapped(cache, technical_details_enabled=False)
    rows = _table_rows(result[1])

    assert len(rows) == 1
    assert _cell_text(rows[0].children[3]) == "2"


def test_general_view_shows_failed_verification_over_verified() -> None:
    """When the same app_name appears with different statuses, the most concerning one is shown."""
    cache = {
        "1.1.1.1|443": _entry(
            ip="1.1.1.1",
            port=443,
            applications={
                "/a.exe": _app(app_name="Widget", app_verification_status="verified"),
            },
        ),
        "2.2.2.2|443": _entry(
            ip="2.2.2.2",
            port=443,
            applications={
                "/b.exe": _app(app_name="Widget", app_verification_status="failed"),
            },
        ),
    }

    result = render_unmapped(cache, technical_details_enabled=False)
    rows = _table_rows(result[1])
    cells = [_cell_text(td) for td in rows[0].children]

    assert cells[2] == "Failed"


def test_general_view_shows_unknown_for_missing_app_name() -> None:
    """Applications with no resolvable app_name are grouped under 'Unknown', not dropped."""
    cache = {
        "203.0.113.7|8443": _entry(
            applications={
                "__unknown_application__": _app(app_name=None, exe=None),
            }
        )
    }

    result = render_unmapped(cache, technical_details_enabled=False)
    rows = _table_rows(result[1])
    cells = [_cell_text(td) for td in rows[0].children]

    assert cells[0] == "Unknown"


def test_general_view_pending_application_shows_retrieving_creator() -> None:
    """An application still awaiting verification shows 'Retrieving...' as its creator."""
    cache = {
        "203.0.113.7|8443": _entry(
            applications={
                "/opt/app.exe": _app(
                    app_name="New App", app_creator=None, app_verification_status=None
                ),
            }
        )
    }

    result = render_unmapped(cache, technical_details_enabled=False)
    rows = _table_rows(result[1])
    cells = [_cell_text(td) for td in rows[0].children]

    assert cells[1] == "Retrieving..."
    assert cells[2] == "Pending"


# --- integration: real UnmappedState wiring ---


def test_render_unmapped_reads_from_real_unmapped_state() -> None:
    """render_unmapped works directly against UnmappedState.cache as merge() produces it."""
    state = UnmappedState()
    state.merge(
        [
            {
                "ip": "203.0.113.7",
                "port": 8443,
                "proto": "tcp",
                "service": "https",
                "process_name": "firefox.exe",
                "pid": 4821,
                "exe": "/opt/firefox.exe",
                "app_name": "Firefox",
                "app_creator": "Mozilla Corporation",
                "app_verification_status": "verified",
                "app_signature_state": None,
                "app_signature_state_details": None,
            }
        ]
    )

    technical = render_unmapped(state.cache, technical_details_enabled=True)
    general = render_unmapped(state.cache, technical_details_enabled=False)

    assert isinstance(technical[1], html.Table)
    assert isinstance(general[1], html.Table)
