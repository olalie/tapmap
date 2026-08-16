"""Windows AppInfo backend: VERSIONINFO, FileSignatureInfo and WinVerifyTrust.

No single Windows API answers all three of AppInfo's questions (name,
creator, verification status) reliably, so this backend combines:
  - VERSIONINFO (windows_version_info.py) for ProductName, CompanyName and
    FileDescription.
  - Microsoft.Security.Extensions.FileSignatureInfo (windows_signature_info.py),
    via the bundled .NET wrapper DLL, as the primary source for signature
    state, state reason and publisher. The wrapper DLL and its native
    redistributable dependency are shipped with the project because this
    isn't available through the standard Python runtime.
  - WinVerifyTrust (windows_trust_override.py), used only as a fallback when
    FileSignatureInfo reports a file as Unsigned, to catch files Windows
    trusts that FileSignatureInfo doesn't recognize correctly.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import windows_signature_info, windows_trust_override, windows_version_info
from .app_info import ApplicationMetadata, VerificationStatus, _get_creator

_TRADEMARK_CHARS = str.maketrans("", "", "®™")


def _is_generic_windows_product_name(product: str) -> bool:
    """Return True if product looks like the generic Windows OS ProductName.

    Observed on real VERSIONINFO data (English and Norwegian Windows
    installs): generic OS components (svchost, PowerShell, Windows Media
    Player, Windows Defender, ...) all place "Windows" immediately after
    "Microsoft", trademark symbols aside - e.g. "Microsoft® Windows®
    Operating System" or the reordered "Operativsystemet Microsoft®
    Windows®". Genuine products like "Windows Terminal" don't follow this
    pattern and are left alone. Matching the fuller phrase "Windows
    Operating System" was tried and rejected - it doesn't survive the
    reordering in the Norwegian string.
    """
    return "Microsoft Windows" in product.translate(_TRADEMARK_CHARS)


def _get_best_app_name(exe_path: str, version_info: dict[str, str | None]) -> str:
    """Return the best application name for display.

    Preference:
      1. ProductName (unless it's the generic Windows OS ProductName)
      2. FileDescription
      3. Executable filename
    """
    product = version_info.get("ProductName")
    description = version_info.get("FileDescription")

    if product and _is_generic_windows_product_name(product):
        product = None

    return product or description or os.path.splitext(os.path.basename(exe_path))[0]


def _resolve_verification_status(signature_state: str | None) -> VerificationStatus:
    """Map a raw signature state to a coarse verification status."""
    if signature_state == "SignedAndTrusted":
        return VerificationStatus.VERIFIED
    if signature_state is None:
        return VerificationStatus.UNKNOWN
    return VerificationStatus.FAILED


class WindowsAppInfoBackend:
    """Resolve ApplicationMetadata using VERSIONINFO, FileSignatureInfo and WinVerifyTrust."""

    def __init__(self, security_extensions_dir: Path) -> None:
        """Load the Microsoft Security Extensions wrapper DLL.

        Raises:
            Exception: on any failure to load the wrapper. Callers are
                responsible for catching this and degrading gracefully.
        """
        windows_signature_info.load(security_extensions_dir)

    def resolve_identity(self, exe_path: str) -> ApplicationMetadata:
        """Resolve name/creator for one executable path (uncached).

        Always defers verification_status to resolve_verification().
        """
        try:
            version_info = windows_version_info.get_version_info(exe_path)
        except OSError:
            version_info = {}

        company_name = version_info.get("CompanyName")

        return ApplicationMetadata(
            name=_get_best_app_name(exe_path, version_info),
            creator=company_name,
            verification_status=None,
            signature_state=None,
            signature_state_details=None,
        )

    def resolve_verification(
        self, exe_path: str, identity: ApplicationMetadata
    ) -> ApplicationMetadata:
        """Resolve code-signing verification for one executable path.

        Finalizes creator from the signing certificate's publisher when
        identity.creator (CompanyName) wasn't available.
        """
        try:
            signature_state, signature_state_details, publisher = (
                windows_signature_info.check_signature(exe_path)
            )
        except Exception:
            signature_state = signature_state_details = publisher = None

        if signature_state == "Unsigned":
            try:
                is_trusted, override_publisher = windows_trust_override.check_trust_override(
                    exe_path
                )
            except OSError:
                is_trusted, override_publisher = False, None

            if is_trusted:
                signature_state = "SignedAndTrusted"
                signature_state_details = "WinVerifyTrustOverride"
                publisher = override_publisher

        creator = _get_creator(identity.creator, publisher)

        return ApplicationMetadata(
            name=identity.name,
            creator=creator,
            verification_status=_resolve_verification_status(signature_state),
            signature_state=signature_state,
            signature_state_details=signature_state_details,
        )
