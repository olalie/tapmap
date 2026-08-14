"""Test CacheViewBuilder's per-service cache merge and hover summary generation."""

from __future__ import annotations

import re
from typing import Any

from tapmap.ui.cache_view import CacheViewBuilder
from tapmap.ui.formatting import country_flag, trust_glyph

_APP_FIELDS = (
    "app_name",
    "app_creator",
    "app_trust",
    "app_signature_state",
    "app_signature_state_details",
)

_DEFAULT_EXE = "/opt/app/app.exe"


def _candidate(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid map candidate (as produced by Model.snapshot())."""
    candidate = {
        "ip": "8.8.8.8",
        "port": 443,
        "proto": "tcp",
        "process_name": None,
        "pid": None,
        "exe": _DEFAULT_EXE,
        "lon": 37.4,
        "lat": -122.1,
        "city": "Mountain View",
        "country": "United States",
        "country_code": "US",
        "asn": 15169,
        "asn_org": "Google LLC",
        "app_name": None,
        "app_creator": None,
        "app_trust": None,
        "app_signature_state": None,
        "app_signature_state_details": None,
    }
    candidate.update(overrides)
    return candidate


def _app_fields(app: dict[str, Any]) -> dict[str, Any]:
    """Return only the app_* fields from an application record."""
    return {field: app.get(field) for field in _APP_FIELDS}


def _entry(
    *, app_name: str | None = None, app_trust: str | None = None, **overrides: Any
) -> dict[str, Any]:
    """Return a minimal ui_cache entry with a single application.

    As consumed by summary-building methods.
    """
    exe_key = app_name or "unknown"
    entry: dict[str, Any] = {
        "ip": "8.8.8.8",
        "port": 443,
        "asn_org": "Google LLC",
        "applications": {
            exe_key: {"app_name": app_name, "app_trust": app_trust},
        },
    }
    entry.update(overrides)
    return entry


def _app_entry(
    *,
    ip: str = "8.8.8.8",
    port: int = 443,
    asn_org: str = "Google LLC",
    exe: str = "/opt/app.exe",
    **app_overrides: Any,
) -> dict[str, Any]:
    """Return a ui_cache entry with one fully-specified application record."""
    app: dict[str, Any] = {
        "app_name": None,
        "app_creator": None,
        "app_trust": None,
        "app_signature_state": None,
        "app_signature_state_details": None,
    }
    app.update(app_overrides)
    return {
        "ip": ip,
        "port": port,
        "asn_org": asn_org,
        "applications": {exe: app},
    }


# --- merge_map_candidates: application record propagation ---


def test_merge_map_candidates_propagates_app_fields_into_new_application() -> None:
    """A new application record carries all five app_* fields from the candidate."""
    builder = CacheViewBuilder()

    candidate = _candidate(
        app_name="Firefox",
        app_creator="Mozilla Corporation",
        app_trust="trusted",
        app_signature_state="SignedAndTrusted",
        app_signature_state_details="None",
    )

    cache = builder.merge_map_candidates({}, [candidate])
    app = cache["8.8.8.8|443"]["applications"][_DEFAULT_EXE]

    assert _app_fields(app) == {
        "app_name": "Firefox",
        "app_creator": "Mozilla Corporation",
        "app_trust": "trusted",
        "app_signature_state": "SignedAndTrusted",
        "app_signature_state_details": "None",
    }


def test_merge_map_candidates_leaves_app_fields_none_when_absent() -> None:
    """A candidate with no app data (AppInfo disabled) leaves app_* fields None."""
    builder = CacheViewBuilder()

    cache = builder.merge_map_candidates({}, [_candidate()])
    app = cache["8.8.8.8|443"]["applications"][_DEFAULT_EXE]

    assert _app_fields(app) == dict.fromkeys(_APP_FIELDS)


def test_merge_map_candidates_backfills_app_fields_on_existing_application() -> None:
    """A later candidate fills in app_* fields that were previously missing."""
    builder = CacheViewBuilder()

    cache = builder.merge_map_candidates({}, [_candidate()])
    cache = builder.merge_map_candidates(
        cache,
        [
            _candidate(
                app_name="Firefox",
                app_creator="Mozilla Corporation",
                app_trust="trusted",
                app_signature_state="SignedAndTrusted",
                app_signature_state_details="None",
            )
        ],
    )
    app = cache["8.8.8.8|443"]["applications"][_DEFAULT_EXE]

    assert app["app_name"] == "Firefox"
    assert app["app_trust"] == "trusted"


def test_merge_map_candidates_keeps_first_app_value_for_same_exe() -> None:
    """A distinct later value for the same exe path does not overwrite the first."""
    builder = CacheViewBuilder()

    cache = builder.merge_map_candidates(
        {}, [_candidate(app_name="Firefox", app_trust="trusted")]
    )
    cache = builder.merge_map_candidates(
        cache, [_candidate(app_name="Other Name", app_trust="not_trusted")]
    )
    app = cache["8.8.8.8|443"]["applications"][_DEFAULT_EXE]

    assert app["app_name"] == "Firefox"
    assert app["app_trust"] == "trusted"


def test_merge_map_candidates_keeps_different_exe_paths_separate() -> None:
    """Two different applications sharing (ip, port) each get their own application record."""
    builder = CacheViewBuilder()

    cache = builder.merge_map_candidates(
        {},
        [
            _candidate(exe="/opt/firefox/firefox.exe", app_name="Firefox", app_trust="trusted"),
            _candidate(exe="/tmp/malware.exe", app_name="Malware", app_trust="not_trusted"),
        ],
    )
    applications = cache["8.8.8.8|443"]["applications"]

    assert applications["/opt/firefox/firefox.exe"]["app_name"] == "Firefox"
    assert applications["/opt/firefox/firefox.exe"]["app_trust"] == "trusted"
    assert applications["/tmp/malware.exe"]["app_name"] == "Malware"
    assert applications["/tmp/malware.exe"]["app_trust"] == "not_trusted"


def test_merge_map_candidates_uses_unknown_bucket_when_exe_missing() -> None:
    """Candidates with no resolvable exe path share a dedicated unknown-application bucket."""
    builder = CacheViewBuilder()

    cache = builder.merge_map_candidates(
        {}, [_candidate(exe=None, process_name="svchost.exe", pid=100)]
    )
    applications = cache["8.8.8.8|443"]["applications"]

    assert CacheViewBuilder._UNKNOWN_APP_KEY in applications
    assert applications[CacheViewBuilder._UNKNOWN_APP_KEY]["processes"] == ["svchost.exe"]


def test_merge_map_candidates_accumulates_processes_within_application() -> None:
    """Multiple processes for the same exe path accumulate in that application's record."""
    builder = CacheViewBuilder()

    cache = builder.merge_map_candidates(
        {},
        [
            _candidate(process_name="Spotify.exe", pid=17840),
            _candidate(process_name="SpotifyLauncher.exe", pid=16696),
        ],
    )
    app = cache["8.8.8.8|443"]["applications"][_DEFAULT_EXE]

    assert app["processes"] == ["Spotify.exe", "SpotifyLauncher.exe"]
    assert app["proc_pids"] == {"Spotify.exe": [17840], "SpotifyLauncher.exe": [16696]}


def test_merge_map_candidates_propagates_country_code() -> None:
    """country_code is propagated the same way as the other geo fields."""
    builder = CacheViewBuilder()

    cache = builder.merge_map_candidates({}, [_candidate(country_code="NO")])
    entry = cache["8.8.8.8|443"]

    assert entry["country_code"] == "NO"


# --- _pick_representative_app: selection rules ---


def test_pick_representative_app_prefers_not_trusted_tier() -> None:
    """A not_trusted app is chosen even with fewer connections than a trusted one."""
    entries = [
        _entry(app_name="Trusted App", app_trust="trusted"),
        _entry(app_name="Trusted App", app_trust="trusted"),
        _entry(app_name="Bad App", app_trust="not_trusted"),
    ]

    name, trust, app_entries, count = CacheViewBuilder._pick_representative_app(entries)

    assert name == "Bad App"
    assert trust == "not_trusted"
    assert len(app_entries) == 1
    assert count == 2


def test_pick_representative_app_prefers_unknown_over_trusted() -> None:
    """An unknown-trust app is chosen over a trusted one."""
    entries = [
        _entry(app_name="Trusted App", app_trust="trusted"),
        _entry(app_name="Mystery App", app_trust="unknown"),
    ]

    name, trust, _, _ = CacheViewBuilder._pick_representative_app(entries)

    assert name == "Mystery App"
    assert trust == "unknown"


def test_pick_representative_app_breaks_tie_by_connection_count() -> None:
    """Within the same trust tier, the app with more connections wins."""
    entries = [
        _entry(app_name="Small App", app_trust="trusted"),
        _entry(app_name="Big App", app_trust="trusted"),
        _entry(app_name="Big App", app_trust="trusted"),
    ]

    name, _, app_entries, _ = CacheViewBuilder._pick_representative_app(entries)

    assert name == "Big App"
    assert len(app_entries) == 2


def test_pick_representative_app_breaks_remaining_tie_alphabetically() -> None:
    """Same trust tier and same connection count breaks tie alphabetically."""
    entries = [
        _entry(app_name="Zebra App", app_trust="trusted"),
        _entry(app_name="Alpha App", app_trust="trusted"),
    ]

    name, _, _, _ = CacheViewBuilder._pick_representative_app(entries)

    assert name == "Alpha App"


def test_pick_representative_app_groups_missing_names_as_unknown() -> None:
    """Connections with no app_name share a single Unknown group."""
    entries = [
        _entry(app_name=None, app_trust=None),
        _entry(app_name=None, app_trust=None),
    ]

    name, trust, app_entries, count = CacheViewBuilder._pick_representative_app(entries)

    assert name == "Unknown"
    assert trust is None
    assert len(app_entries) == 2
    assert count == 1


def test_pick_representative_app_returns_unknown_for_no_applications() -> None:
    """Entries with no applications at all produce the empty/Unknown result."""
    entries = [{"ip": "8.8.8.8", "port": 443, "applications": {}}]

    name, trust, app_entries, count = CacheViewBuilder._pick_representative_app(entries)

    assert name == "Unknown"
    assert trust is None
    assert app_entries == []
    assert count == 0


# --- _format_summary_row: alignment ---


def test_format_summary_row_aligns_value_regardless_of_icon_width() -> None:
    """Value text starts at the same column whether or not a row has an icon."""
    row_with_wide_icon = CacheViewBuilder._format_summary_row("Location:", "XX", "value")
    row_without_icon = CacheViewBuilder._format_summary_row("Network operator:", "  ", "value")
    row_with_narrow_icon = CacheViewBuilder._format_summary_row("App:", "X ", "value")

    assert row_with_wide_icon.index("value") == row_without_icon.index("value")
    assert row_without_icon.index("value") == row_with_narrow_icon.index("value")


# --- _build_app_summary: integration ---


def test_build_app_summary_shows_location_with_flag() -> None:
    """Location row shows city, country and the matching flag."""
    entries = [_entry(app_name="Firefox", app_trust="trusted")]

    summary = CacheViewBuilder()._build_app_summary(
        place="Kansas City, United States", country_code="US", entries=entries
    )

    location_line = summary.split("<br>")[0]
    assert country_flag("US") in location_line
    assert "Kansas City, United States" in location_line


def test_build_app_summary_scopes_network_operator_to_selected_app() -> None:
    """The shown network operator belongs to the representative app, not the point."""
    entries = [
        _entry(app_name="Safe App", app_trust="trusted", asn_org="Org A"),
        _entry(app_name="Bad App", app_trust="not_trusted", asn_org="Org B1"),
        _entry(app_name="Bad App", app_trust="not_trusted", asn_org="Org B2"),
    ]

    summary = CacheViewBuilder()._build_app_summary(
        place="Somewhere", country_code=None, entries=entries
    )

    operators_line = summary.split("<br>")[1]
    assert "Org A" not in operators_line
    assert "Org B1" in operators_line
    assert "+1" not in operators_line


def test_build_app_summary_appends_count_for_additional_apps() -> None:
    """+N reflects the number of unique apps beyond the one shown."""
    entries = [
        _entry(app_name="App One", app_trust="not_trusted"),
        _entry(app_name="App Two", app_trust="trusted"),
        _entry(app_name="App Three", app_trust="trusted"),
    ]

    summary = CacheViewBuilder()._build_app_summary(
        place="Somewhere", country_code=None, entries=entries
    )

    apps_line = summary.split("<br>")[2]
    assert "App One +2" in apps_line
    assert trust_glyph("not_trusted") in apps_line


def test_build_app_summary_omits_count_for_single_app() -> None:
    """No +N suffix appears when only one unique app is present."""
    entries = [_entry(app_name="Only App", app_trust="trusted")]

    summary = CacheViewBuilder()._build_app_summary(
        place="Somewhere", country_code=None, entries=entries
    )

    apps_line = summary.split("<br>")[2]
    assert "Only App" in apps_line
    assert "+" not in apps_line


def test_build_app_summary_uses_singular_labels() -> None:
    """Location, network operator and app labels are all singular."""
    entries = [_entry(app_name="Solo App", app_trust="trusted")]

    summary = CacheViewBuilder()._build_app_summary(
        place="Somewhere", country_code=None, entries=entries
    )

    assert "Network operator:" in summary
    assert "Network operators:" not in summary
    assert "App:" in summary
    assert "Apps:" not in summary


def test_build_app_summary_uses_colored_bullet_trust_indicator() -> None:
    """The app row's trust indicator is a single colored bullet character."""
    entries = [_entry(app_name="Solo App", app_trust="trusted")]

    summary = CacheViewBuilder()._build_app_summary(
        place="Somewhere", country_code=None, entries=entries
    )

    apps_line = summary.split("<br>")[2]
    assert "■" in apps_line
    assert "#00ff66" in apps_line


def test_build_app_summary_aligns_app_value_with_other_rows() -> None:
    """The app name starts at the same rendered column as the location and operator values.

    HTML markup is stripped before comparing, since tags consume no visual
    width when rendered but would otherwise skew a raw string index.
    """
    entries = [_entry(app_name="Spotify", app_trust="trusted", asn_org="Google LLC")]

    summary = CacheViewBuilder()._build_app_summary(
        place="United States", country_code="US", entries=entries
    )

    location_line, operators_line, apps_line = summary.split("<br>")
    location_rendered = re.sub(r"<[^>]+>", "", location_line)
    operators_rendered = re.sub(r"<[^>]+>", "", operators_line)
    apps_rendered = re.sub(r"<[^>]+>", "", apps_line)

    assert location_rendered.index("United States") == operators_rendered.index("Google LLC")
    assert operators_rendered.index("Google LLC") == apps_rendered.index("Spotify")


# --- _format_procs_with_pids: multi-application rendering ---


def test_format_procs_with_pids_combines_multiple_applications() -> None:
    """Procs text lists processes from every application, sorted alphabetically."""
    builder = CacheViewBuilder()
    entry = {
        "applications": {
            "/opt/spotify/Spotify.exe": {
                "processes": ["Spotify.exe"],
                "proc_pids": {"Spotify.exe": [17840]},
            },
            "/opt/spotify/SpotifyLauncher.exe": {
                "processes": ["SpotifyLauncher.exe"],
                "proc_pids": {"SpotifyLauncher.exe": [16696]},
            },
        }
    }

    text = builder._format_procs_with_pids(entry)

    assert text == "Spotify.exe (pid 17840), SpotifyLauncher.exe (pid 16696)"


def test_format_procs_with_pids_returns_placeholder_for_no_applications() -> None:
    """An entry with no applications formats as '-'."""
    builder = CacheViewBuilder()

    assert builder._format_procs_with_pids({"applications": {}}) == "-"


# --- build_view_from_cache: mode selection and multi-application behavior ---


def test_build_view_from_cache_technical_details_off_uses_app_summary() -> None:
    """technical_details_enabled=False produces the application-oriented summary."""
    builder = CacheViewBuilder()

    cache = builder.merge_map_candidates(
        {}, [_candidate(app_name="Firefox", app_trust="trusted")]
    )
    view = builder.build_view_from_cache(cache, technical_details_enabled=False)

    assert "Firefox" in view["summaries"]["0"]


def test_build_view_from_cache_technical_details_on_matches_existing_format() -> None:
    """technical_details_enabled=True leaves the connection-oriented hover summary unchanged.

    The click-details panel now shows the app name via its own App: field
    (see _format_process_blocks), but never creator or trust wording.
    """
    builder = CacheViewBuilder()

    cache = builder.merge_map_candidates(
        {},
        [_candidate(app_name="Firefox", app_creator="Mozilla Corp", app_trust="trusted")],
    )
    view = builder.build_view_from_cache(cache, technical_details_enabled=True)

    summary = view["summaries"]["0"]
    detail = view["details"]["0"]

    assert "Firefox" not in summary
    assert "Mozilla" not in summary
    assert "trusted" not in summary.lower()

    assert "Firefox" in detail
    assert "Mozilla" not in detail
    assert "trusted" not in detail.lower()


def test_build_view_from_cache_shows_untrusted_app_sharing_endpoint_with_trusted_app() -> None:
    """A not_trusted application is never hidden by a trusted application at the same endpoint."""
    builder = CacheViewBuilder()

    cache = builder.merge_map_candidates(
        {},
        [
            _candidate(exe="/opt/firefox/firefox.exe", app_name="Firefox", app_trust="trusted"),
            _candidate(exe="/tmp/malware.exe", app_name="Malware", app_trust="not_trusted"),
        ],
    )
    view = builder.build_view_from_cache(cache, technical_details_enabled=False)

    assert "Malware" in view["summaries"]["0"]


def test_build_click_details_shows_processes_from_multiple_applications() -> None:
    """Technical Details lists processes from every application at an endpoint."""
    builder = CacheViewBuilder()

    cache = builder.merge_map_candidates(
        {},
        [
            _candidate(
                exe="/opt/firefox/firefox.exe",
                process_name="firefox.exe",
                pid=1000,
                app_name="Firefox",
                app_trust="trusted",
            ),
            _candidate(
                exe="/tmp/malware.exe",
                process_name="malware.exe",
                pid=2000,
                app_name="Malware",
                app_trust="not_trusted",
            ),
        ],
    )
    view = builder.build_view_from_cache(cache, technical_details_enabled=True)
    detail = view["details"]["0"]

    assert "firefox.exe (pid 1000)" in detail
    assert "malware.exe (pid 2000)" in detail


def test_format_process_blocks_elides_long_executable_path() -> None:
    """The Executable: line shows a middle-elided path, not the full raw path."""
    long_exe = (
        r"C:\Program Files\WindowsApps\Microsoft.StartExperiencesApp_1.380.2.0_x64"
        r"__8wekyb3d8bbwe\MicrosoftStartFeedProvider\MicrosoftStartFeedProvider.exe"
    )
    entry = {
        "applications": {
            long_exe: {
                "app_name": "MicrosoftStartFeedProvider",
                "processes": ["MicrosoftStartFeedProvider.exe"],
                "proc_pids": {},
            },
        },
    }

    _, _, exe_line = CacheViewBuilder()._format_process_blocks(entry)
    visible_text = re.sub(r"<[^>]+>", "", exe_line)

    assert long_exe not in visible_text
    assert r"C:\Program Files\WindowsApps\...\MicrosoftStartFeedProvider.exe" in visible_text


# --- _format_org_block / _format_process_blocks: Process:/App:/Executable: layout ---


def test_format_org_block_shows_process_app_and_executable_fields() -> None:
    """Each process block shows Process:, App:, and Executable: for its application."""
    entry = {
        "ip": "8.8.8.8",
        "port": 443,
        "proto": "tcp",
        "applications": {
            "/opt/firefox/firefox.exe": {
                "app_name": "Firefox",
                "processes": ["firefox.exe"],
                "proc_pids": {"firefox.exe": [1000]},
            },
        },
    }

    block = CacheViewBuilder()._format_org_block("Org A", [entry])

    assert "Process:" in block
    assert "firefox.exe (pid 1000)" in block
    assert "App:" in block
    assert "Firefox" in block
    assert "Executable:" in block
    assert "/opt/firefox/firefox.exe" in block


def test_display_exe_wraps_resolved_path_with_full_path_attribute() -> None:
    """A resolved executable is wrapped in an <exe full="..."> tag carrying the raw path."""
    result = CacheViewBuilder()._display_exe(r"C:\opt\app.exe")

    assert result == r'<exe full="C:\opt\app.exe">C:\opt\app.exe</exe>'


def test_display_exe_does_not_wrap_unknown_executable() -> None:
    """An unresolved executable shows plain 'Unknown', not wrapped in a tag."""
    result = CacheViewBuilder()._display_exe(CacheViewBuilder._UNKNOWN_APP_KEY)

    assert result == "Unknown"


def test_format_org_block_shows_unknown_for_unresolved_executable() -> None:
    """A process with no resolvable exe path shows 'Unknown' on the Executable: line."""
    entry = {
        "ip": "8.8.8.8",
        "port": 443,
        "proto": "tcp",
        "applications": {
            CacheViewBuilder._UNKNOWN_APP_KEY: {
                "app_name": None,
                "processes": ["svchost.exe"],
                "proc_pids": {},
            },
        },
    }

    block = CacheViewBuilder()._format_org_block("Org A", [entry])

    assert "Executable:" in block
    assert "Unknown" in block
    assert CacheViewBuilder._UNKNOWN_APP_KEY not in block


def test_format_org_block_separates_multiple_process_blocks_with_one_blank_line() -> None:
    """Multiple applications at one connection get exactly one blank line between blocks."""
    entry = {
        "ip": "8.8.8.8",
        "port": 443,
        "proto": "tcp",
        "applications": {
            "/opt/a.exe": {"app_name": "App A", "processes": ["a.exe"], "proc_pids": {}},
            "/opt/b.exe": {"app_name": "App B", "processes": ["b.exe"], "proc_pids": {}},
        },
    }

    block = CacheViewBuilder()._format_org_block("Org A", [entry])

    assert block.split("\n").count("") == 1


def test_format_org_block_has_no_blank_line_between_connections() -> None:
    """Two connections in the same org are not separated by a blank line."""
    entries = [
        {
            "ip": "8.8.8.8",
            "port": 443,
            "proto": "tcp",
            "applications": {
                "/opt/a.exe": {"app_name": "App A", "processes": ["a.exe"], "proc_pids": {}},
            },
        },
        {
            "ip": "1.1.1.1",
            "port": 443,
            "proto": "tcp",
            "applications": {
                "/opt/b.exe": {"app_name": "App B", "processes": ["b.exe"], "proc_pids": {}},
            },
        },
    ]

    block = CacheViewBuilder()._format_org_block("Org A", entries)

    assert "" not in block.split("\n")


def test_format_process_blocks_aligns_values_in_same_column() -> None:
    """Process:, App:, and Executable: values start at the same rendered column.

    HTML markup is stripped before comparing, since tags consume no visual
    width when rendered but would otherwise skew a raw string index.
    """
    entry = {
        "applications": {
            "/opt/firefox/firefox.exe": {
                "app_name": "Firefox",
                "processes": ["firefox.exe"],
                "proc_pids": {"firefox.exe": [1000]},
            },
        },
    }

    process_line, app_line, exe_line = CacheViewBuilder()._format_process_blocks(entry)
    exe_visible = re.sub(r"<[^>]+>", "", exe_line)

    assert process_line.index("firefox.exe") == app_line.index("Firefox")
    assert app_line.index("Firefox") == exe_visible.index("/opt/firefox/firefox.exe")


# --- _build_app_click_details: Non-Technical click-details panel ---


def test_build_app_click_details_shows_location_once() -> None:
    """The location line appears exactly once, regardless of entry count."""
    entries = [
        _app_entry(exe="/a.exe", app_name="App A", asn_org="Org A"),
        _app_entry(exe="/b.exe", app_name="App B", asn_org="Org B"),
    ]

    details = CacheViewBuilder()._build_app_click_details(
        place="Oslo, Norway", country_code="NO", entries=entries
    )

    assert details.count("Location:") == 1
    assert "Oslo, Norway" in details
    assert country_flag("NO") in details


def test_build_app_click_details_groups_by_network_operator() -> None:
    """Applications are grouped under their own 'Network operator:' section."""
    entries = [
        _app_entry(exe="/a.exe", app_name="App A", asn_org="Org A"),
        _app_entry(exe="/b.exe", app_name="App B", asn_org="Org B"),
    ]

    details = CacheViewBuilder()._build_app_click_details(
        place="Somewhere", country_code=None, entries=entries
    )

    assert "Network operator: Org A" in details
    assert "Network operator: Org B" in details
    org_a_index = details.index("Network operator: Org A")
    app_a_index = details.index("App A")
    org_b_index = details.index("Network operator: Org B")
    assert org_a_index < app_a_index < org_b_index


def test_build_app_click_details_deduplicates_same_exe_within_operator() -> None:
    """The same exe path appearing across multiple entries is shown once."""
    entries = [
        _app_entry(port=443, exe="/a.exe", app_name="App A", asn_org="Org A"),
        _app_entry(port=8080, exe="/a.exe", app_name="App A", asn_org="Org A"),
    ]

    details = CacheViewBuilder()._build_app_click_details(
        place="Somewhere", country_code=None, entries=entries
    )

    assert details.count("App A") == 1


def test_build_app_click_details_deduplicates_same_named_app_across_different_exes() -> None:
    """Different exe paths that would render identically collapse to one line.

    Mirrors OneDrive shipping several binaries (OneDrive.exe,
    FileSyncHelper.exe, ...) that all report the same app_name, creator, and
    trust - the compact view has no exe column, so repeats add noise, not
    information.
    """
    entries = [
        _app_entry(
            port=443,
            exe="/OneDrive.exe",
            app_name="Microsoft OneDrive",
            app_creator="Microsoft Corporation",
            app_trust="trusted",
            app_signature_state="TrustedAndSigned",
        ),
        _app_entry(
            port=8080,
            exe="/FileSyncHelper.exe",
            app_name="Microsoft OneDrive",
            app_creator="Microsoft Corporation",
            app_trust="trusted",
            app_signature_state="TrustedAndSigned",
        ),
    ]

    details = CacheViewBuilder()._build_app_click_details(
        place="Somewhere", country_code=None, entries=entries
    )

    assert details.count("Microsoft OneDrive") == 1


def test_build_app_click_details_keeps_differently_trusted_same_named_apps_separate() -> None:
    """Two exe paths sharing a display name but differing in trust are not collapsed."""
    entries = [
        _app_entry(
            port=443,
            exe="/a.exe",
            app_name="Widget",
            app_creator="Vendor",
            app_trust="trusted",
            app_signature_state="TrustedAndSigned",
        ),
        _app_entry(
            port=8080,
            exe="/b.exe",
            app_name="Widget",
            app_creator="Vendor",
            app_trust="not_trusted",
            app_signature_state="Unsigned",
        ),
    ]

    details = CacheViewBuilder()._build_app_click_details(
        place="Somewhere", country_code=None, entries=entries
    )

    assert details.count("Widget") == 2


def test_build_app_click_details_lists_different_exe_paths_separately() -> None:
    """Two different applications sharing an operator both get their own line."""
    entries = [
        _app_entry(
            exe="/firefox.exe", app_name="Firefox", app_trust="trusted", asn_org="Org A"
        ),
        _app_entry(
            exe="/malware.exe", app_name="Malware", app_trust="not_trusted", asn_org="Org A"
        ),
    ]

    details = CacheViewBuilder()._build_app_click_details(
        place="Somewhere", country_code=None, entries=entries
    )

    assert "Firefox" in details
    assert "Malware" in details


def test_build_app_click_details_sorts_not_trusted_first() -> None:
    """Within a network operator, not_trusted applications are listed before trusted ones."""
    entries = [
        _app_entry(
            exe="/trusted.exe", app_name="Trusted App", app_trust="trusted", asn_org="Org A"
        ),
        _app_entry(
            exe="/bad.exe", app_name="Bad App", app_trust="not_trusted", asn_org="Org A"
        ),
    ]

    details = CacheViewBuilder()._build_app_click_details(
        place="Somewhere", country_code=None, entries=entries
    )

    assert details.index("Bad App") < details.index("Trusted App")


def test_build_app_click_details_uses_humanized_state_with_details() -> None:
    """Windows-style signature state and details render as 'State: details'."""
    entries = [
        _app_entry(
            app_name="Firefox",
            app_creator="Mozilla Corporation",
            app_trust="trusted",
            app_signature_state="TrustedAndSigned",
            app_signature_state_details="Verified publisher",
        )
    ]

    details = CacheViewBuilder()._build_app_click_details(
        place="Somewhere", country_code=None, entries=entries
    )
    visible = re.sub(r"<[^>]+>", "", details)

    assert "Firefox (Mozilla Corporation, Trusted and signed: Verified publisher)" in visible


def test_build_app_click_details_uses_humanized_state_without_details() -> None:
    """Signature state with no details renders as just the humanized state."""
    entries = [
        _app_entry(
            app_name="Firefox",
            app_creator="Mozilla Corporation",
            app_signature_state="SignatureInvalid",
        )
    ]

    details = CacheViewBuilder()._build_app_click_details(
        place="Somewhere", country_code=None, entries=entries
    )
    visible = re.sub(r"<[^>]+>", "", details)

    assert "Firefox (Mozilla Corporation, Signature invalid)" in visible


def test_build_app_click_details_renders_macos_developer_signed_with_notarized_details() -> None:
    """MacOS's DeveloperSigned/Notarized state renders through the same generic pipeline."""
    entries = [
        _app_entry(
            app_name="TapMap",
            app_creator="Tip Teknologi i Praksis AS",
            app_trust="trusted",
            app_signature_state="DeveloperSigned",
            app_signature_state_details="Notarized",
        )
    ]

    details = CacheViewBuilder()._build_app_click_details(
        place="Somewhere", country_code=None, entries=entries
    )
    visible = re.sub(r"<[^>]+>", "", details)

    assert "TapMap (Tip Teknologi i Praksis AS, Developer signed: Notarized)" in visible


def test_build_app_click_details_ignores_literal_none_details_string() -> None:
    """A details value of the literal string 'None' is treated as no details."""
    entries = [
        _app_entry(
            app_name="Firefox",
            app_signature_state="TrustedAndSigned",
            app_signature_state_details="None",
        )
    ]

    details = CacheViewBuilder()._build_app_click_details(
        place="Somewhere", country_code=None, entries=entries
    )
    visible = re.sub(r"<[^>]+>", "", details)

    assert "Trusted and signed)" in visible


def test_build_app_click_details_falls_back_to_trust_level_without_state() -> None:
    """With no signature state, the raw trust level is shown."""
    entries = [_app_entry(app_name="Some App", app_trust="unknown")]

    details = CacheViewBuilder()._build_app_click_details(
        place="Somewhere", country_code=None, entries=entries
    )
    visible = re.sub(r"<[^>]+>", "", details)

    assert "Some App (Unknown creator, unknown)" in visible


def test_format_app_line_colorizes_only_the_trust_status_text() -> None:
    """The trust status uses the trust color; app name and creator stay plain."""
    app = {
        "app_name": "Firefox",
        "app_creator": "Mozilla Corporation",
        "app_trust": "trusted",
        "app_signature_state": "TrustedAndSigned",
        "app_signature_state_details": None,
    }

    line = CacheViewBuilder()._format_app_line(app)

    assert line == (
        'Firefox (Mozilla Corporation, '
        '<span style="color:#00ff66">Trusted and signed</span>)'
    )


def test_format_app_line_uses_not_trusted_color_for_unsigned() -> None:
    """A not_trusted application's status text uses the not_trusted color."""
    app = {
        "app_name": "Malware",
        "app_creator": None,
        "app_trust": "not_trusted",
        "app_signature_state": "Unsigned",
        "app_signature_state_details": None,
    }

    line = CacheViewBuilder()._format_app_line(app)

    assert '<span style="color:#ff4444">Unsigned</span>' in line


def test_build_app_click_details_includes_trust_status_note() -> None:
    """The trust-status disclaimer is always present."""
    entries = [_app_entry(app_name="App A")]

    details = CacheViewBuilder()._build_app_click_details(
        place="Somewhere", country_code=None, entries=entries
    )

    assert "Trust status is evaluated by the operating system, not by TapMap." in details


def test_build_app_click_details_never_shows_process_pid_ip_or_port() -> None:
    """No process, PID, IP, or port text ever appears in the Non-Technical panel."""
    entries = [
        {
            "ip": "8.8.8.8",
            "port": 443,
            "asn_org": "Google LLC",
            "applications": {
                "/opt/app.exe": {
                    "app_name": "App A",
                    "app_creator": "Vendor",
                    "app_trust": "trusted",
                    "processes": ["app.exe"],
                    "proc_pids": {"app.exe": [1234]},
                }
            },
        }
    ]

    details = CacheViewBuilder()._build_app_click_details(
        place="Somewhere", country_code=None, entries=entries
    )

    assert "8.8.8.8" not in details
    assert "443" not in details
    assert "app.exe" not in details
    assert "1234" not in details


def test_build_view_from_cache_technical_details_off_uses_app_click_details() -> None:
    """technical_details_enabled=False routes click details through the new builder."""
    builder = CacheViewBuilder()

    cache = builder.merge_map_candidates(
        {},
        [
            _candidate(
                app_name="Firefox", app_creator="Mozilla Corporation", app_trust="trusted"
            )
        ],
    )
    view = builder.build_view_from_cache(cache, technical_details_enabled=False)
    detail = view["details"]["0"]

    assert "Network operator:" in detail
    assert "Firefox" in detail
    assert "Trust status is evaluated by the operating system, not by TapMap." in detail
    assert "Services:" not in detail


def test_build_view_from_cache_technical_details_on_details_unchanged() -> None:
    """technical_details_enabled=True still produces the Technical connection-oriented details.

    The org header stays the bare organization name (no 'Network operator:'
    label), matching the Non-Technical view's own, differently-labeled section.
    """
    builder = CacheViewBuilder()

    cache = builder.merge_map_candidates(
        {}, [_candidate(app_name="Firefox", app_trust="trusted")]
    )
    view = builder.build_view_from_cache(cache, technical_details_enabled=True)
    detail = view["details"]["0"]

    assert "Services:" in detail
    assert "Network operator:" not in detail
    assert "App:" in detail
    assert "Firefox" in detail
