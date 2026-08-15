"""Linux AppInfo backend: dpkg/apt package provenance (Debian/Ubuntu only)."""

from __future__ import annotations

import os

from . import linux_package_info
from .app_info import ApplicationMetadata, VerificationStatus, _get_creator


def _get_best_app_name(exe_path: str, package: str) -> str:
    """Return the best application name for display.

    Preference:
      1. The package's one unambiguous, visible .desktop entry name.
      2. The dpkg package name.
      3. Executable filename.
    """
    desktop_name = linux_package_info.find_desktop_name(package)
    return desktop_name or package or os.path.splitext(os.path.basename(exe_path))[0]


class LinuxAppInfoBackend:
    """Resolve ApplicationMetadata using dpkg package ownership and apt repo provenance."""

    def resolve(self, exe_path: str) -> ApplicationMetadata:
        """Resolve application metadata for one executable path (uncached)."""
        real_path = os.path.realpath(exe_path)
        package = linux_package_info.find_owning_package(real_path)

        if package is None:
            return ApplicationMetadata(
                name=os.path.splitext(os.path.basename(exe_path))[0],
                creator=_get_creator(None, None),
                verification_status=VerificationStatus.UNKNOWN,
                signature_state="Unpackaged",
                signature_state_details=None,
            )

        name = _get_best_app_name(exe_path, package)
        creator = _get_creator(linux_package_info.find_creator(package), None)

        if not linux_package_info.verify_package_integrity(package, real_path):
            return ApplicationMetadata(
                name=name,
                creator=creator,
                verification_status=VerificationStatus.FAILED,
                signature_state="PackageModified",
                signature_state_details=None,
            )

        if not linux_package_info.is_repo_backed(package):
            return ApplicationMetadata(
                name=name,
                creator=creator,
                verification_status=VerificationStatus.UNKNOWN,
                signature_state="PackageSourceUnverified",
                signature_state_details=None,
            )

        return ApplicationMetadata(
            name=name,
            creator=creator,
            verification_status=VerificationStatus.VERIFIED,
            signature_state="PackageVerified",
            signature_state_details=None,
        )
