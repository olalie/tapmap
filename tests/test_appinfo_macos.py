"""Test the macOS AppInfo backend: name resolution, verification-status mapping, and orchestration."""  # noqa: E501

from __future__ import annotations

import pytest

from tapmap.model.appinfo import VerificationStatus
from tapmap.model.appinfo import macos_bundle_info as bundle_info
from tapmap.model.appinfo import macos_signature_info as sig_info
from tapmap.model.appinfo.app_info import ApplicationMetadata
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


# --- MacOSAppInfoBackend.resolve_identity(): fast, synchronous, always runs ---


def test_resolve_identity_defers_for_macho_executable(monkeypatch) -> None:
    """A readable Mach-O file resolves name but defers verification_status and creator."""
    backend = MacOSAppInfoBackend()

    monkeypatch.setattr(
        bundle_info,
        "get_bundle_info",
        lambda path: {"CFBundleName": "Foo", "CFBundleDisplayName": None},
    )
    monkeypatch.setattr(sig_info, "is_macho", lambda path: True)

    identity = backend.resolve_identity("/Applications/Foo.app/Contents/MacOS/Foo")

    assert identity.name == "Foo"
    assert identity.creator is None
    assert identity.verification_status is None
    assert identity.signature_state is None


def test_resolve_identity_not_applicable_for_non_macho(monkeypatch) -> None:
    """A non-Mach-O file (e.g. a shell script) is a terminal NotApplicable/UNKNOWN."""
    backend = MacOSAppInfoBackend()

    monkeypatch.setattr(bundle_info, "get_bundle_info", lambda path: {})
    monkeypatch.setattr(sig_info, "is_macho", lambda path: False)

    identity = backend.resolve_identity("/opt/homebrew/bin/brew")

    assert identity.verification_status == VerificationStatus.UNKNOWN
    assert identity.signature_state == "NotApplicable"
    assert identity.signature_state_details == "Not a Mach-O executable"
    assert identity.creator == "Unknown"


def test_resolve_identity_unknown_when_macho_check_fails(monkeypatch) -> None:
    """An unreadable file (is_macho returns None) is a terminal UNKNOWN, not a false negative."""
    backend = MacOSAppInfoBackend()

    monkeypatch.setattr(bundle_info, "get_bundle_info", lambda path: {})
    monkeypatch.setattr(sig_info, "is_macho", lambda path: None)

    identity = backend.resolve_identity("/tmp/gone")

    assert identity.verification_status == VerificationStatus.UNKNOWN
    assert identity.signature_state is None
    assert identity.signature_state_details is None


# --- MacOSAppInfoBackend.resolve_verification(): expensive, deferred, orchestration ---


def _identity(*, name: str = "Foo") -> ApplicationMetadata:
    """Return a minimal deferred identity result, as resolve_identity() would produce."""
    return ApplicationMetadata(
        name=name,
        creator=None,
        verification_status=None,
        signature_state=None,
        signature_state_details=None,
    )


def test_resolve_verification_developer_signed_app(monkeypatch) -> None:
    """A Developer ID signed, non-notarized app resolves creator and verification from codesign."""
    backend = MacOSAppInfoBackend()

    monkeypatch.setattr(
        sig_info, "check_signature", lambda path: ("DeveloperSigned", None, "Foo Ltd")
    )
    monkeypatch.setattr(sig_info, "check_notarized", lambda path: False)

    metadata = backend.resolve_verification(
        "/Applications/Foo.app/Contents/MacOS/Foo", _identity()
    )

    assert metadata.name == "Foo"
    assert metadata.creator == "Foo Ltd"
    assert metadata.verification_status == VerificationStatus.VERIFIED
    assert metadata.signature_state == "DeveloperSigned"
    assert metadata.signature_state_details is None


def test_resolve_verification_developer_signed_and_notarized_app(monkeypatch) -> None:
    """Notarization is recorded as details, not folded into a combined state."""
    backend = MacOSAppInfoBackend()

    monkeypatch.setattr(
        sig_info, "check_signature", lambda path: ("DeveloperSigned", None, "Foo Ltd")
    )
    monkeypatch.setattr(sig_info, "check_notarized", lambda path: True)

    metadata = backend.resolve_verification(
        "/Applications/Foo.app/Contents/MacOS/Foo", _identity()
    )

    assert metadata.signature_state == "DeveloperSigned"
    assert metadata.signature_state_details == "Notarized"
    assert metadata.verification_status == VerificationStatus.VERIFIED


def test_resolve_verification_apple_system(monkeypatch) -> None:
    """A Software Signing chain resolves to AppleSystem/VERIFIED."""
    backend = MacOSAppInfoBackend()

    monkeypatch.setattr(sig_info, "check_signature", lambda path: ("AppleSystem", None, "Apple"))
    monkeypatch.setattr(sig_info, "check_notarized", lambda path: False)

    metadata = backend.resolve_verification("/usr/bin/curl", _identity())

    assert metadata.verification_status == VerificationStatus.VERIFIED
    assert metadata.creator == "Apple"
    assert metadata.signature_state == "AppleSystem"


def test_resolve_verification_unknown_when_signature_check_fails_unexpectedly(monkeypatch) -> None:
    """An unexpected signature-check failure resolves to UNKNOWN, never FAILED."""
    backend = MacOSAppInfoBackend()

    monkeypatch.setattr(sig_info, "check_signature", lambda path: (None, None, None))

    metadata = backend.resolve_verification("/tmp/whatever", _identity())

    assert metadata.verification_status == VerificationStatus.UNKNOWN
    assert metadata.signature_state is None
    assert metadata.signature_state_details is None


def test_resolve_verification_unrecognized_publisher_falls_back_to_unknown_creator(
    monkeypatch,
) -> None:
    """A verified state with no parsed publisher still resolves creator to Unknown."""
    backend = MacOSAppInfoBackend()

    monkeypatch.setattr(
        sig_info, "check_signature", lambda path: ("DeveloperSigned", None, None)
    )
    monkeypatch.setattr(sig_info, "check_notarized", lambda path: False)

    metadata = backend.resolve_verification("/opt/homebrew/bin/tool", _identity())

    assert metadata.creator == "Unknown"
    assert metadata.verification_status == VerificationStatus.VERIFIED
