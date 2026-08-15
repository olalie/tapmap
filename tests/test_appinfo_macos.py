"""Test the macOS AppInfo backend: name resolution, verification-status mapping, and orchestration."""  # noqa: E501

from __future__ import annotations

import pytest

from tapmap.model.appinfo import VerificationStatus
from tapmap.model.appinfo import macos_bundle_info as bundle_info
from tapmap.model.appinfo import macos_signature_info as sig_info
from tapmap.model.appinfo.appinfo_macos import (
    MacOSAppInfoBackend,
    _get_best_app_name,
    _resolve_verification_status,
)

# --- pure helpers: name/verification-status resolution ---


def test_get_best_app_name_prefers_display_name() -> None:
    """CFBundleDisplayName wins over CFBundleName and filename."""
    name = _get_best_app_name(
        "/Applications/Foo.app/Contents/MacOS/Foo",
        {"CFBundleDisplayName": "Foo Display", "CFBundleName": "Foo"},
    )
    assert name == "Foo Display"


def test_get_best_app_name_falls_back_to_bundle_name() -> None:
    """CFBundleName is used when CFBundleDisplayName is absent (e.g. Firefox's real plist)."""
    name = _get_best_app_name(
        "/Applications/Firefox.app/Contents/MacOS/firefox",
        {"CFBundleDisplayName": None, "CFBundleName": "Firefox"},
    )
    assert name == "Firefox"


def test_get_best_app_name_falls_back_to_filename() -> None:
    """The executable's filename is used when there's no bundle info at all."""
    name = _get_best_app_name("/opt/homebrew/bin/git", {})
    assert name == "git"


@pytest.mark.parametrize("state", ["AppleSystem", "DeveloperSigned", "AppStoreSigned"])
def test_resolve_verification_status_known_good_states_are_verified(state: str) -> None:
    """A recognized signing identity, notarized or not, maps to VERIFIED."""
    assert _resolve_verification_status(state) == VerificationStatus.VERIFIED


@pytest.mark.parametrize("state", ["AdHoc", "Invalid", "Unsigned"])
def test_resolve_verification_status_known_bad_states_fail(state: str) -> None:
    """Any definitively-known failing state maps to FAILED."""
    assert _resolve_verification_status(state) == VerificationStatus.FAILED


@pytest.mark.parametrize("state", ["NotApplicable", None])
def test_resolve_verification_status_not_applicable_or_missing_is_unknown(
    state: str | None,
) -> None:
    """Neither a non-Mach-O file nor a failed check is a negative verification signal."""
    assert _resolve_verification_status(state) == VerificationStatus.UNKNOWN


# --- MacOSAppInfoBackend.resolve(): orchestration (data sources mocked) ---


def test_resolve_developer_signed_app(monkeypatch) -> None:
    """A Developer ID signed, non-notarized app combines bundle info and signature data."""
    backend = MacOSAppInfoBackend()

    monkeypatch.setattr(
        bundle_info,
        "get_bundle_info",
        lambda path: {"CFBundleName": "Foo", "CFBundleDisplayName": None},
    )
    monkeypatch.setattr(sig_info, "is_macho", lambda path: True)
    monkeypatch.setattr(
        sig_info, "check_signature", lambda path: ("DeveloperSigned", None, "Foo Ltd")
    )
    monkeypatch.setattr(sig_info, "check_notarized", lambda path: False)

    metadata = backend.resolve("/Applications/Foo.app/Contents/MacOS/Foo")

    assert metadata.name == "Foo"
    assert metadata.creator == "Foo Ltd"
    assert metadata.verification_status == VerificationStatus.VERIFIED
    assert metadata.signature_state == "DeveloperSigned"
    assert metadata.signature_state_details is None


def test_resolve_developer_signed_and_notarized_app(monkeypatch) -> None:
    """Notarization is recorded as details, not folded into a combined state."""
    backend = MacOSAppInfoBackend()

    monkeypatch.setattr(bundle_info, "get_bundle_info", lambda path: {"CFBundleName": "Foo"})
    monkeypatch.setattr(sig_info, "is_macho", lambda path: True)
    monkeypatch.setattr(
        sig_info, "check_signature", lambda path: ("DeveloperSigned", None, "Foo Ltd")
    )
    monkeypatch.setattr(sig_info, "check_notarized", lambda path: True)

    metadata = backend.resolve("/Applications/Foo.app/Contents/MacOS/Foo")

    assert metadata.signature_state == "DeveloperSigned"
    assert metadata.signature_state_details == "Notarized"
    assert metadata.verification_status == VerificationStatus.VERIFIED


def test_resolve_apple_system(monkeypatch) -> None:
    """A Software Signing chain resolves to AppleSystem/VERIFIED."""
    backend = MacOSAppInfoBackend()

    monkeypatch.setattr(bundle_info, "get_bundle_info", lambda path: {})
    monkeypatch.setattr(sig_info, "is_macho", lambda path: True)
    monkeypatch.setattr(sig_info, "check_signature", lambda path: ("AppleSystem", None, "Apple"))
    monkeypatch.setattr(sig_info, "check_notarized", lambda path: False)

    metadata = backend.resolve("/usr/bin/curl")

    assert metadata.verification_status == VerificationStatus.VERIFIED
    assert metadata.creator == "Apple"
    assert metadata.signature_state == "AppleSystem"


def test_resolve_not_applicable_for_non_macho(monkeypatch) -> None:
    """A non-Mach-O file (e.g. a shell script) resolves to NotApplicable/UNKNOWN."""
    backend = MacOSAppInfoBackend()

    monkeypatch.setattr(bundle_info, "get_bundle_info", lambda path: {})
    monkeypatch.setattr(sig_info, "is_macho", lambda path: False)

    metadata = backend.resolve("/opt/homebrew/bin/brew")

    assert metadata.verification_status == VerificationStatus.UNKNOWN
    assert metadata.signature_state == "NotApplicable"
    assert metadata.signature_state_details == "Not a Mach-O executable"
    assert metadata.creator == "Unknown"


def test_resolve_unknown_when_macho_check_fails(monkeypatch) -> None:
    """An unreadable file (is_macho returns None) resolves to UNKNOWN, not a false negative."""
    backend = MacOSAppInfoBackend()

    monkeypatch.setattr(bundle_info, "get_bundle_info", lambda path: {})
    monkeypatch.setattr(sig_info, "is_macho", lambda path: None)

    metadata = backend.resolve("/tmp/gone")

    assert metadata.verification_status == VerificationStatus.UNKNOWN
    assert metadata.signature_state is None
    assert metadata.signature_state_details is None


def test_resolve_unknown_when_signature_check_fails_unexpectedly(monkeypatch) -> None:
    """An unexpected signature-check failure resolves to UNKNOWN, never FAILED."""
    backend = MacOSAppInfoBackend()

    monkeypatch.setattr(bundle_info, "get_bundle_info", lambda path: {})
    monkeypatch.setattr(sig_info, "is_macho", lambda path: True)
    monkeypatch.setattr(sig_info, "check_signature", lambda path: (None, None, None))

    metadata = backend.resolve("/tmp/whatever")

    assert metadata.verification_status == VerificationStatus.UNKNOWN
    assert metadata.signature_state is None
    assert metadata.signature_state_details is None


def test_resolve_unrecognized_publisher_falls_back_to_unknown_without_affecting_verification_status(
    monkeypatch,
    ) -> None:
    """A verified state with no parsed publisher still resolves creator to Unknown."""
    backend = MacOSAppInfoBackend()

    monkeypatch.setattr(bundle_info, "get_bundle_info", lambda path: {})
    monkeypatch.setattr(sig_info, "is_macho", lambda path: True)
    monkeypatch.setattr(
        sig_info, "check_signature", lambda path: ("DeveloperSigned", None, None)
    )
    monkeypatch.setattr(sig_info, "check_notarized", lambda path: False)

    metadata = backend.resolve("/opt/homebrew/bin/tool")

    assert metadata.creator == "Unknown"
    assert metadata.verification_status == VerificationStatus.VERIFIED
