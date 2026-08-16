"""Test the Windows AppInfo backend: name/verification-status heuristics and resolution orchestration."""  # noqa: E501

from __future__ import annotations

import pytest

from tapmap.model.appinfo import VerificationStatus
from tapmap.model.appinfo import windows_signature_info as signature_info
from tapmap.model.appinfo import windows_trust_override as trust_override
from tapmap.model.appinfo import windows_version_info as version_info
from tapmap.model.appinfo.app_info import ApplicationMetadata
from tapmap.model.appinfo.appinfo_windows import (
    WindowsAppInfoBackend,
    _get_best_app_name,
    _is_generic_windows_product_name,
    _resolve_verification_status,
)

# --- pure helpers: name/verification-status resolution ---


def test_get_best_app_name_prefers_product_name() -> None:
    """ProductName wins over FileDescription and filename."""
    name = _get_best_app_name(
        r"C:\apps\foo.exe",
        {"ProductName": "Contoso Suite", "FileDescription": "Contoso launcher"},
    )
    assert name == "Contoso Suite"


def test_get_best_app_name_skips_generic_windows_product_name() -> None:
    """A ProductName matching the generic Windows OS pattern is skipped."""
    name = _get_best_app_name(
        r"C:\windows\system32\foo.exe",
        {"ProductName": "Microsoft Windows Operating System", "FileDescription": "Foo Host"},
    )
    assert name == "Foo Host"


# --- generic Windows OS ProductName detection ---
#
# These cases are taken from real VERSIONINFO data observed on Windows
# system binaries (English and Norwegian installs), not hypothetical
# examples. They document why the heuristic checks for "Microsoft"
# immediately followed by "Windows" rather than either "Windows" alone
# (too broad - wrongly matches real products like Windows Terminal) or
# the fuller phrase "Windows Operating System" (too narrow - doesn't
# survive the word reordering in the Norwegian string).


def test_is_generic_windows_product_name_matches_english_os_string() -> None:
    """The real English generic ProductName (seen on lsass.exe) is detected."""
    assert _is_generic_windows_product_name("Microsoft® Windows® Operating System") is True


def test_is_generic_windows_product_name_matches_localized_os_string() -> None:
    """The real Norwegian generic ProductName (seen on svchost.exe etc.) is detected.

    "Operativsystemet" ("The operating system") is reordered to the front,
    so "Windows Operating System" is not a substring here - only the
    "Microsoft" + "Windows" adjacency survives translation.
    """
    assert _is_generic_windows_product_name("Operativsystemet Microsoft® Windows®") is True


def test_is_generic_windows_product_name_does_not_match_real_product() -> None:
    """Windows Terminal's real ProductName is not treated as generic.

    Its ProductName is "Windows Terminal" - no "Microsoft" immediately
    before "Windows" - unlike every generic OS-component string observed.
    """
    assert _is_generic_windows_product_name("Windows Terminal") is False


def test_get_best_app_name_skips_generic_windows_product_name_with_trademark_symbols() -> None:
    """The real lsass.exe VERSIONINFO falls back to FileDescription."""
    name = _get_best_app_name(
        r"C:\Windows\System32\lsass.exe",
        {
            "ProductName": "Microsoft® Windows® Operating System",
            "FileDescription": "Local Security Authority Process",
        },
    )
    assert name == "Local Security Authority Process"


def test_get_best_app_name_skips_localized_generic_windows_product_name() -> None:
    """The real (Norwegian) svchost.exe VERSIONINFO falls back to FileDescription."""
    name = _get_best_app_name(
        r"C:\Windows\System32\svchost.exe",
        {
            "ProductName": "Operativsystemet Microsoft® Windows®",
            "FileDescription": "Vertsprosess for Windows-tjenester",
        },
    )
    assert name == "Vertsprosess for Windows-tjenester"


def test_get_best_app_name_keeps_windows_terminal_product_name() -> None:
    """Windows Terminal's own ProductName is used, not suppressed as generic."""
    name = _get_best_app_name(
        r"C:\...\wt.exe",
        {
            "ProductName": "Windows Terminal",
            "FileDescription": "Windows Terminal Host",
        },
    )
    assert name == "Windows Terminal"


def test_get_best_app_name_falls_back_to_file_description() -> None:
    """FileDescription is used when ProductName is absent."""
    name = _get_best_app_name(
        r"C:\apps\foo.exe", {"ProductName": None, "FileDescription": "Foo Helper"}
    )
    assert name == "Foo Helper"


def test_get_best_app_name_falls_back_to_filename() -> None:
    """The executable's filename is used when VERSIONINFO has nothing usable."""
    name = _get_best_app_name("/apps/foo.exe", {})
    assert name == "foo"


def test_resolve_verification_status_signed_and_trusted() -> None:
    """SignedAndTrusted maps to VERIFIED."""
    assert _resolve_verification_status("SignedAndTrusted") == VerificationStatus.VERIFIED


@pytest.mark.parametrize("state", ["SignedAndNotTrusted", "Invalid", "Unsigned"])
def test_resolve_verification_status_known_bad_states_fail(state: str) -> None:
    """Any definitively failing signature state maps to FAILED."""
    assert _resolve_verification_status(state) == VerificationStatus.FAILED


def test_resolve_verification_status_none_is_unknown() -> None:
    """A missing/failed signature check maps to UNKNOWN, not FAILED."""
    assert _resolve_verification_status(None) == VerificationStatus.UNKNOWN


# --- WindowsAppInfoBackend.resolve_identity(): fast, synchronous, always runs ---


def _bare_backend() -> WindowsAppInfoBackend:
    """Return a WindowsAppInfoBackend without loading the real wrapper DLL."""
    return object.__new__(WindowsAppInfoBackend)


def test_resolve_identity_uses_version_info_and_always_defers(monkeypatch) -> None:
    """Identity resolves name/CompanyName from VERSIONINFO and always defers verification."""
    backend = _bare_backend()

    monkeypatch.setattr(
        version_info,
        "get_version_info",
        lambda path: {"ProductName": "Contoso Suite", "CompanyName": "Contoso Ltd"},
    )

    identity = backend.resolve_identity(r"C:\Apps\Foo.exe")

    assert identity.name == "Contoso Suite"
    assert identity.creator == "Contoso Ltd"
    assert identity.verification_status is None
    assert identity.signature_state is None


def test_resolve_identity_leaves_creator_unresolved_when_company_name_absent(monkeypatch) -> None:
    """No CompanyName in VERSIONINFO leaves creator None, to be resolved from the publisher later."""  # noqa: E501
    backend = _bare_backend()

    monkeypatch.setattr(version_info, "get_version_info", lambda path: {})

    identity = backend.resolve_identity(r"C:\Apps\Foo.exe")

    assert identity.creator is None


# --- WindowsAppInfoBackend.resolve_verification(): expensive, deferred, orchestration ---


def _identity(*, name: str = "Foo", creator: str | None = None) -> ApplicationMetadata:
    """Return a minimal deferred identity result, as resolve_identity() would produce."""
    return ApplicationMetadata(
        name=name,
        creator=creator,
        verification_status=None,
        signature_state=None,
        signature_state_details=None,
    )


def test_resolve_verification_combines_signature_with_identity(monkeypatch) -> None:
    """A signed, trusted file's verification_status/signature_state come from the signature check."""  # noqa: E501
    backend = _bare_backend()

    monkeypatch.setattr(
        signature_info,
        "check_signature",
        lambda path: ("SignedAndTrusted", "None", "Contoso Ltd"),
    )

    metadata = backend.resolve_verification(
        r"C:\Apps\Foo.exe", _identity(name="Contoso Suite", creator="Contoso Ltd")
    )

    assert metadata.name == "Contoso Suite"
    assert metadata.creator == "Contoso Ltd"
    assert metadata.verification_status == VerificationStatus.VERIFIED
    assert metadata.signature_state == "SignedAndTrusted"


def test_resolve_verification_uses_identity_creator_over_publisher(monkeypatch) -> None:
    """CompanyName (identity.creator) wins over the signing certificate's publisher."""
    backend = _bare_backend()

    monkeypatch.setattr(
        signature_info,
        "check_signature",
        lambda path: ("SignedAndTrusted", "None", "Some Other Signer"),
    )

    metadata = backend.resolve_verification(
        r"C:\Apps\Foo.exe", _identity(creator="Contoso Ltd")
    )

    assert metadata.creator == "Contoso Ltd"


def test_resolve_verification_falls_back_to_publisher_when_identity_creator_absent(
    monkeypatch,
) -> None:
    """No CompanyName means creator finalizes from the signing certificate's publisher."""
    backend = _bare_backend()

    monkeypatch.setattr(
        signature_info,
        "check_signature",
        lambda path: ("SignedAndTrusted", "None", "Contoso Ltd"),
    )

    metadata = backend.resolve_verification(r"C:\Apps\Foo.exe", _identity(creator=None))

    assert metadata.creator == "Contoso Ltd"


def test_resolve_verification_falls_back_to_trust_override_when_unsigned(monkeypatch) -> None:
    """Unsigned files consult WinVerifyTrust as a fallback."""
    backend = _bare_backend()

    monkeypatch.setattr(
        signature_info, "check_signature", lambda path: ("Unsigned", "None", None)
    )
    monkeypatch.setattr(
        trust_override, "check_trust_override", lambda path: (True, "Override Publisher")
    )

    metadata = backend.resolve_verification(r"C:\Apps\Foo.exe", _identity(creator=None))

    assert metadata.signature_state == "SignedAndTrusted"
    assert metadata.signature_state_details == "WinVerifyTrustOverride"
    assert metadata.creator == "Override Publisher"
    assert metadata.verification_status == VerificationStatus.VERIFIED


def test_resolve_verification_does_not_consult_trust_override_when_already_signed(
    monkeypatch,
) -> None:
    """WinVerifyTrust is only consulted when FileSignatureInfo reports Unsigned."""
    backend = _bare_backend()

    calls: list[str] = []

    monkeypatch.setattr(
        signature_info,
        "check_signature",
        lambda path: ("SignedAndNotTrusted", "NotTrusted", "Suspicious Publisher"),
    )
    monkeypatch.setattr(
        trust_override,
        "check_trust_override",
        lambda path: calls.append(path) or (True, "Should not be used"),
    )

    metadata = backend.resolve_verification(r"C:\Apps\Foo.exe", _identity(creator=None))

    assert calls == []
    assert metadata.verification_status == VerificationStatus.FAILED
    assert metadata.creator == "Suspicious Publisher"
