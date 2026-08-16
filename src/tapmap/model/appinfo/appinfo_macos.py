"""macOS AppInfo backend: Info.plist, codesign and spctl."""

from __future__ import annotations

import os

from . import macos_bundle_info, macos_signature_info
from .app_info import ApplicationMetadata, VerificationStatus, _get_creator

_VERIFICATION_STATUS_BY_STATE: dict[str | None, VerificationStatus] = {
    "AppleSystem": VerificationStatus.VERIFIED,
    "DeveloperSigned": VerificationStatus.VERIFIED,
    "AppStoreSigned": VerificationStatus.VERIFIED,
    "AdHoc": VerificationStatus.FAILED,
    "Invalid": VerificationStatus.FAILED,
    "Unsigned": VerificationStatus.FAILED,
}


def _resolve_verification_status(signature_state: str | None) -> VerificationStatus:
    """Map a raw signature state to a coarse verification status."""
    return _VERIFICATION_STATUS_BY_STATE.get(signature_state, VerificationStatus.UNKNOWN)


def _get_best_app_name(exe_path: str, bundle_info: dict[str, str | None]) -> str:
    """Return the best application name for display.

    Preference:
      1. CFBundleDisplayName
      2. CFBundleName
      3. Executable filename
    """
    display_name = bundle_info.get("CFBundleDisplayName")
    name = bundle_info.get("CFBundleName")
    return display_name or name or os.path.splitext(os.path.basename(exe_path))[0]


class MacOSAppInfoBackend:
    """Resolve ApplicationMetadata using Info.plist, codesign and spctl."""

    def resolve_identity(self, exe_path: str) -> ApplicationMetadata:
        """Resolve name for one executable path (uncached).

        Terminal for a file that isn't a Mach-O executable, or couldn't be
        read at all. Otherwise defers both verification_status and creator
        to resolve_verification().
        """
        bundle_info = macos_bundle_info.get_bundle_info(exe_path)
        name = _get_best_app_name(exe_path, bundle_info)

        macho = macos_signature_info.is_macho(exe_path)

        if macho is None:
            return ApplicationMetadata(
                name=name,
                creator=_get_creator(None, None),
                verification_status=VerificationStatus.UNKNOWN,
                signature_state=None,
                signature_state_details=None,
            )

        if not macho:
            return ApplicationMetadata(
                name=name,
                creator=_get_creator(None, None),
                verification_status=VerificationStatus.UNKNOWN,
                signature_state="NotApplicable",
                signature_state_details="Not a Mach-O executable",
            )

        return ApplicationMetadata(
            name=name,
            creator=None,
            verification_status=None,
            signature_state=None,
            signature_state_details=None,
        )

    def resolve_verification(
        self, exe_path: str, identity: ApplicationMetadata
    ) -> ApplicationMetadata:
        """Resolve code-signing verification for one Mach-O executable path.

        Only called when resolve_identity() found a readable Mach-O file.
        """
        signature_state, signature_state_details, publisher = (
            macos_signature_info.check_signature(exe_path)
        )

        if signature_state == "DeveloperSigned" and macos_signature_info.check_notarized(
            exe_path
        ):
            signature_state_details = "Notarized"

        return ApplicationMetadata(
            name=identity.name,
            creator=_get_creator(None, publisher),
            verification_status=_resolve_verification_status(signature_state),
            signature_state=signature_state,
            signature_state_details=signature_state_details,
        )
