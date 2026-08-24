"""Tests for UI formatting helpers."""

from __future__ import annotations

from tapmap.ui.formatting import (
    PENDING_VERIFICATION_STATUS,
    display_verification_status,
    elide_path_middle,
    humanize_camel_case,
    verification_status_color,
    verification_status_glyph,
)


def test_verification_status_color_pending_is_white() -> None:
    """A pending verification status renders as white, distinct from unknown's yellow."""
    assert verification_status_color(PENDING_VERIFICATION_STATUS) == "#ffffff"


def test_verification_status_color_unknown_is_yellow() -> None:
    """An unresolved-but-terminal (unknown) status stays yellow, not white."""
    assert verification_status_color("unknown") == "#ffff00"
    assert verification_status_color(None) == "#ffff00"


def test_verification_status_glyph_pending_is_white_bullet() -> None:
    """The pending glyph is a colored bullet using the white pending color."""
    assert verification_status_glyph(PENDING_VERIFICATION_STATUS) == (
        '<span style="color:#ffffff">■</span>'
    )


def test_display_verification_status_pending_for_real_exe() -> None:
    """A real application with no verification_status yet displays as pending."""
    app = {"app_name": "Firefox", "app_verification_status": None, "exe": "/firefox.exe"}

    assert display_verification_status(app) == "pending"


def test_display_verification_status_unknown_bucket_stays_none() -> None:
    """The synthetic unknown-application bucket (no exe) is never treated as pending."""
    app = {"app_name": None, "app_verification_status": None, "exe": None}

    assert display_verification_status(app) is None


def test_display_verification_status_passes_through_resolved_values() -> None:
    """A resolved verification_status is returned unchanged, regardless of exe."""
    app = {"app_verification_status": "failed", "exe": "/malware.exe"}

    assert display_verification_status(app) == "failed"


def test_humanize_camel_case_splits_multiple_words() -> None:
    """PascalCase text becomes space-separated, lowercased after the first word."""
    assert humanize_camel_case("TrustedAndSigned") == "Trusted and signed"


def test_humanize_camel_case_splits_two_words() -> None:
    """A two-word PascalCase value splits into two words."""
    assert humanize_camel_case("SignatureInvalid") == "Signature invalid"


def test_humanize_camel_case_single_word_is_unchanged() -> None:
    """A single word with no case boundary is returned as-is."""
    assert humanize_camel_case("Trusted") == "Trusted"


def test_humanize_camel_case_empty_string_returns_empty_string() -> None:
    """An empty string is returned unchanged."""
    assert humanize_camel_case("") == ""


def test_elide_path_middle_leaves_short_path_unchanged() -> None:
    """A path already within max_length is returned as-is."""
    path = r"C:\Windows\System32\svchost.exe"

    assert elide_path_middle(path) == path


def test_elide_path_middle_leaves_shallow_long_name_unchanged() -> None:
    """A short two-level path is returned as-is, even though it isn't tiny."""
    path = r"C:\Program Files\Mozilla Firefox\firefox.exe"

    assert elide_path_middle(path) == path


def test_elide_path_middle_collapses_deep_path_keeping_two_levels() -> None:
    """A long, deep path keeps the drive, first two directories, and filename."""
    path = (
        r"C:\Program Files\WindowsApps\Microsoft.StartExperiencesApp_1.380.2.0_x64"
        r"__8wekyb3d8bbwe\MicrosoftStartFeedProvider\MicrosoftStartFeedProvider.exe"
    )

    result = elide_path_middle(path)

    assert result == r"C:\Program Files\WindowsApps\...\MicrosoftStartFeedProvider.exe"


def test_elide_path_middle_never_splits_a_component() -> None:
    """Every collapsed segment is a whole original component, "...", or the filename."""
    path = (
        r"C:\Program Files\WindowsApps\Microsoft.StartExperiencesApp_1.380.2.0_x64"
        r"__8wekyb3d8bbwe\MicrosoftStartFeedProvider\MicrosoftStartFeedProvider.exe"
    )
    original_components = set(path.split("\\"))

    result = elide_path_middle(path)

    for component in result.split("\\"):
        assert component == "..." or component in original_components


def test_elide_path_middle_keeps_only_middle_level_when_just_one_exists() -> None:
    """A long path with only one collapsible directory level is left unchanged.

    Nothing can be omitted without either dropping the required drive/filename
    or truncating mid-component, so no ellipsis is inserted.
    """
    path = "C:\\" + "A" * 80 + r"\file.exe"

    assert elide_path_middle(path) == path


def test_elide_path_middle_leaves_drive_and_filename_only_path_unchanged() -> None:
    """A path with no directory components at all has nothing to collapse."""
    path = "C:\\" + "x" * 80 + ".exe"

    assert elide_path_middle(path) == path


def test_elide_path_middle_collapses_realistic_user_profile_path() -> None:
    """A realistic, moderately deep path collapses once it exceeds max_length."""
    path = r"C:\Users\ola\AppData\Local\Programs\Microsoft VS Code\Code.exe"

    assert elide_path_middle(path) == r"C:\Users\ola\...\Code.exe"


def test_elide_path_middle_preserves_full_executable_filename() -> None:
    """The executable filename is never shortened, even when the path collapses."""
    cases = [
        (r"C:\Users\ola\AppData\Local\Programs\Microsoft VS Code\Code.exe", "Code.exe"),
        (
            r"C:\Program Files\WindowsApps\Microsoft.StartExperiencesApp_1.380.2.0_x64"
            r"__8wekyb3d8bbwe\MicrosoftStartFeedProvider\MicrosoftStartFeedProvider.exe",
            "MicrosoftStartFeedProvider.exe",
        ),
    ]

    for path, filename in cases:
        assert elide_path_middle(path).endswith(filename)


def test_elide_path_middle_inserts_exactly_one_ellipsis_when_collapsing() -> None:
    """Collapsed output contains exactly one "..." component, never more."""
    cases = [
        r"C:\Users\ola\AppData\Local\Programs\Microsoft VS Code\Code.exe",
        (
            r"C:\Program Files\WindowsApps\Microsoft.StartExperiencesApp_1.380.2.0_x64"
            r"__8wekyb3d8bbwe\MicrosoftStartFeedProvider\MicrosoftStartFeedProvider.exe"
        ),
    ]

    for path in cases:
        result = elide_path_middle(path)
        assert result.split("\\").count("...") == 1


def test_elide_path_middle_boundary_at_max_length() -> None:
    """A path exactly at max_length is unchanged; one character longer collapses.

    Both paths share the same drive, three directory levels, and filename;
    only the padding inserted into the filename differs by one character, so
    crossing max_length is the only meaningful difference between them.
    """
    max_length = 60
    prefix = "C:\\Dir1\\Dir2\\Dir3\\"
    filename = "file.exe"
    pad_len = max_length - len(prefix) - len(filename)

    at_limit = prefix + ("x" * pad_len) + filename
    over_limit = prefix + ("x" * (pad_len + 1)) + filename

    assert len(at_limit) == max_length
    assert len(over_limit) == max_length + 1

    assert elide_path_middle(at_limit, max_length=max_length) == at_limit

    expected_collapsed = "C:\\Dir1\\Dir2\\...\\" + ("x" * (pad_len + 1)) + filename
    assert elide_path_middle(over_limit, max_length=max_length) == expected_collapsed
