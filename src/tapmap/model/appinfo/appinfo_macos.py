"""macOS AppInfo backend: Info.plist, codesign and spctl."""

from __future__ import annotations

import os

from . import macos_bundle_info, macos_signature_info
from .app_info import ApplicationMetadata, TrustVerdict, _get_creator

_TRUST_BY_STATE: dict[str | None, TrustVerdict] = {
    "AppleSystem": TrustVerdict.TRUSTED,
    "DeveloperSigned": TrustVerdict.TRUSTED,
    "AppStoreSigned": TrustVerdict.TRUSTED,
    "AdHoc": TrustVerdict.NOT_TRUSTED,
    "Invalid": TrustVerdict.NOT_TRUSTED,
    "Unsigned": TrustVerdict.NOT_TRUSTED,
}


def _resolve_trust(signature_state: str | None) -> TrustVerdict:
    """Map a raw signature state to a coarse trust verdict."""
    return _TRUST_BY_STATE.get(signature_state, TrustVerdict.UNKNOWN)


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

    def resolve(self, exe_path: str) -> ApplicationMetadata:
        """Resolve application metadata for one executable path (uncached)."""
        bundle_info = macos_bundle_info.get_bundle_info(exe_path)
        name = _get_best_app_name(exe_path, bundle_info)

        macho = macos_signature_info.is_macho(exe_path)

        if macho is None:
            return ApplicationMetadata(
                name=name,
                creator=_get_creator(None, None),
                trust=TrustVerdict.UNKNOWN,
                signature_state=None,
                signature_state_details=None,
            )

        if not macho:
            return ApplicationMetadata(
                name=name,
                creator=_get_creator(None, None),
                trust=TrustVerdict.UNKNOWN,
                signature_state="NotApplicable",
                signature_state_details="Not a Mach-O executable",
            )

        signature_state, signature_state_details, publisher = (
            macos_signature_info.check_signature(exe_path)
        )

        if signature_state == "DeveloperSigned" and macos_signature_info.check_notarized(
            exe_path
        ):
            signature_state_details = "Notarized"

        return ApplicationMetadata(
            name=name,
            creator=_get_creator(None, publisher),
            trust=_resolve_trust(signature_state),
            signature_state=signature_state,
            signature_state_details=signature_state_details,
        )
