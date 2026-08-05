"""Test CacheViewBuilder's per-service cache merge and hover summary generation."""

from __future__ import annotations

from typing import Any

from tapmap.ui.cache_view import CacheViewBuilder
from tapmap.ui.formatting import country_flag, trust_glyph

_APP_FIELDS = (
    "app_name",
    "app_creator",
    "app_trust",
    "app_signature_state",
    "app_signature_state_reason",
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
        "app_signature_state_reason": None,
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
        "app_signature_state_reason": None,
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
        app_signature_state_reason="None",
    )

    cache = builder.merge_map_candidates({}, [candidate])
    app = cache["8.8.8.8|443"]["applications"][_DEFAULT_EXE]

    assert _app_fields(app) == {
        "app_name": "Firefox",
        "app_creator": "Mozilla Corporation",
        "app_trust": "trusted",
        "app_signature_state": "SignedAndTrusted",
        "app_signature_state_reason": "None",
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
                app_signature_state_reason="None",
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
    row_with_wide_icon = CacheViewBuilder._format_summary_row("Location:", "XX", 2, "value")
    row_without_icon = CacheViewBuilder._format_summary_row("Network operators:", "", 0, "value")
    row_with_narrow_icon = CacheViewBuilder._format_summary_row("Apps:", "X", 1, "value")

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
    assert "Org B1 +1" in operators_line


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
    """technical_details_enabled=True leaves the connection-oriented summary unchanged."""
    builder = CacheViewBuilder()

    cache = builder.merge_map_candidates(
        {}, [_candidate(app_name="Firefox", app_trust="trusted")]
    )
    view = builder.build_view_from_cache(cache, technical_details_enabled=True)

    summary = view["summaries"]["0"]
    detail = view["details"]["0"]

    for text in (summary, detail):
        assert "Firefox" not in text
        assert "Mozilla" not in text
        assert "trusted" not in text.lower()


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


def test_build_app_click_details_uses_humanized_state_with_reason() -> None:
    """Windows-style signature state and reason render as 'State: reason'."""
    entries = [
        _app_entry(
            app_name="Firefox",
            app_creator="Mozilla Corporation",
            app_trust="trusted",
            app_signature_state="TrustedAndSigned",
            app_signature_state_reason="Verified publisher",
        )
    ]

    details = CacheViewBuilder()._build_app_click_details(
        place="Somewhere", country_code=None, entries=entries
    )

    assert "Firefox (Mozilla Corporation, Trusted and signed: Verified publisher)" in details


def test_build_app_click_details_uses_humanized_state_without_reason() -> None:
    """Signature state with no reason renders as just the humanized state."""
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

    assert "Firefox (Mozilla Corporation, Signature invalid)" in details


def test_build_app_click_details_ignores_literal_none_reason_string() -> None:
    """A reason of the literal string 'None' is treated as no reason."""
    entries = [
        _app_entry(
            app_name="Firefox",
            app_signature_state="TrustedAndSigned",
            app_signature_state_reason="None",
        )
    ]

    details = CacheViewBuilder()._build_app_click_details(
        place="Somewhere", country_code=None, entries=entries
    )

    assert "Trusted and signed)" in details


def test_build_app_click_details_falls_back_to_trust_level_without_state() -> None:
    """With no signature state, the raw trust level is shown."""
    entries = [_app_entry(app_name="Some App", app_trust="unknown")]

    details = CacheViewBuilder()._build_app_click_details(
        place="Somewhere", country_code=None, entries=entries
    )

    assert "Some App (Unknown creator, unknown)" in details


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
    """technical_details_enabled=True still produces the Technical connection-oriented details."""
    builder = CacheViewBuilder()

    cache = builder.merge_map_candidates(
        {}, [_candidate(app_name="Firefox", app_trust="trusted")]
    )
    view = builder.build_view_from_cache(cache, technical_details_enabled=True)
    detail = view["details"]["0"]

    assert "Services:" in detail
    assert "Network operator:" not in detail
    assert "Firefox" not in detail
