"""Test the Windows AppInfo backend: name/trust heuristics and resolution orchestration."""

from __future__ import annotations

import pytest

from tapmap.model.appinfo import TrustVerdict
from tapmap.model.appinfo import windows_signature_info as signature_info
from tapmap.model.appinfo import windows_trust_override as trust_override
from tapmap.model.appinfo import windows_version_info as version_info
from tapmap.model.appinfo.appinfo_windows import (
    WindowsAppInfoBackend,
    _get_best_app_name,
    _is_generic_windows_product_name,
    _resolve_trust,
)

# --- pure helpers: name/trust resolution ---


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


def test_resolve_trust_signed_and_trusted() -> None:
    """SignedAndTrusted maps to TRUSTED."""
    assert _resolve_trust("SignedAndTrusted") == TrustVerdict.TRUSTED


@pytest.mark.parametrize("state", ["SignedAndNotTrusted", "Invalid", "Unsigned"])
def test_resolve_trust_known_bad_states_are_not_trusted(state: str) -> None:
    """Any definitively-known non-trusted state maps to NOT_TRUSTED."""
    assert _resolve_trust(state) == TrustVerdict.NOT_TRUSTED


def test_resolve_trust_none_is_unknown() -> None:
    """A missing/failed signature check maps to UNKNOWN, not NOT_TRUSTED."""
    assert _resolve_trust(None) == TrustVerdict.UNKNOWN


# --- WindowsAppInfoBackend.resolve(): orchestration (data sources mocked) ---


def _bare_backend() -> WindowsAppInfoBackend:
    """Return a WindowsAppInfoBackend without loading the real wrapper DLL."""
    return object.__new__(WindowsAppInfoBackend)


def test_resolve_combines_version_info_and_signature(monkeypatch) -> None:
    """A signed, trusted file combines VERSIONINFO and signature data."""
    backend = _bare_backend()

    monkeypatch.setattr(
        version_info,
        "get_version_info",
        lambda path: {"ProductName": "Contoso Suite", "CompanyName": "Contoso Ltd"},
    )
    monkeypatch.setattr(
        signature_info,
        "check_signature",
        lambda path: ("SignedAndTrusted", "None", "Contoso Ltd"),
    )

    metadata = backend.resolve(r"C:\Apps\Foo.exe")

    assert metadata.name == "Contoso Suite"
    assert metadata.creator == "Contoso Ltd"
    assert metadata.trust == TrustVerdict.TRUSTED
    assert metadata.signature_state == "SignedAndTrusted"


def test_resolve_falls_back_to_trust_override_when_unsigned(monkeypatch) -> None:
    """Unsigned files consult WinVerifyTrust as a fallback."""
    backend = _bare_backend()

    monkeypatch.setattr(version_info, "get_version_info", lambda path: {})
    monkeypatch.setattr(
        signature_info, "check_signature", lambda path: ("Unsigned", "None", None)
    )
    monkeypatch.setattr(
        trust_override, "check_trust_override", lambda path: (True, "Override Publisher")
    )

    metadata = backend.resolve(r"C:\Apps\Foo.exe")

    assert metadata.signature_state == "SignedAndTrusted"
    assert metadata.signature_state_details == "WinVerifyTrustOverride"
    assert metadata.creator == "Override Publisher"
    assert metadata.trust == TrustVerdict.TRUSTED


def test_resolve_does_not_consult_trust_override_when_already_signed(monkeypatch) -> None:
    """WinVerifyTrust is only consulted when FileSignatureInfo reports Unsigned."""
    backend = _bare_backend()

    calls: list[str] = []

    monkeypatch.setattr(version_info, "get_version_info", lambda path: {})
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

    metadata = backend.resolve(r"C:\Apps\Foo.exe")

    assert calls == []
    assert metadata.trust == TrustVerdict.NOT_TRUSTED
    assert metadata.creator == "Suspicious Publisher"
