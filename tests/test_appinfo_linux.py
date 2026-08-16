"""Test the Linux AppInfo backend: name resolution, verification-status mapping, and orchestration."""  # noqa: E501

from __future__ import annotations

import os
import platform
from pathlib import Path

import pytest

from tapmap.model.appinfo import VerificationStatus
from tapmap.model.appinfo import linux_package_info as pkg_info
from tapmap.model.appinfo.app_info import ApplicationMetadata
from tapmap.model.appinfo.appinfo_linux import LinuxAppInfoBackend, _get_best_app_name
from tapmap.ui.formatting import humanize_camel_case

# --- pure helpers: name resolution ---


def test_get_best_app_name_prefers_desktop_name(monkeypatch) -> None:
    """The package's .desktop display name wins over the package name and filename."""
    monkeypatch.setattr(pkg_info, "find_desktop_name", lambda package: "Visual Studio Code")

    assert _get_best_app_name("/usr/share/code/code", "code") == "Visual Studio Code"


def test_get_best_app_name_falls_back_to_package_name(monkeypatch) -> None:
    """The dpkg package name is used when there's no .desktop entry (e.g. a CLI tool)."""
    monkeypatch.setattr(pkg_info, "find_desktop_name", lambda package: None)

    assert _get_best_app_name("/usr/bin/curl", "curl") == "curl"


# --- LinuxAppInfoBackend.resolve_identity(): fast, synchronous, always runs ---


def test_resolve_identity_owned_package_defers_verification(monkeypatch) -> None:
    """A package-owned executable resolves name/creator but defers verification_status."""
    monkeypatch.setattr(pkg_info, "find_owning_package", lambda path: "curl")
    monkeypatch.setattr(pkg_info, "find_desktop_name", lambda package: None)
    monkeypatch.setattr(pkg_info, "find_creator", lambda package: None)
    backend = LinuxAppInfoBackend()

    identity = backend.resolve_identity("/usr/bin/curl")

    assert identity.name == "curl"
    assert identity.creator == "Unknown"
    assert identity.verification_status is None
    assert identity.signature_state is None


def test_resolve_identity_unpackaged_executable_is_terminal_unknown(monkeypatch) -> None:
    """An executable owned by no dpkg package is a terminal UNKNOWN - nothing to defer."""
    monkeypatch.setattr(pkg_info, "find_owning_package", lambda path: None)
    backend = LinuxAppInfoBackend()

    identity = backend.resolve_identity("/snap/firefox/current/usr/lib/firefox/firefox")

    assert identity.name == "firefox"
    assert identity.creator == "Unknown"
    assert identity.verification_status == VerificationStatus.UNKNOWN
    assert identity.signature_state == "Unpackaged"
    assert humanize_camel_case(identity.signature_state) == "Unpackaged"


@pytest.mark.skipif(
    platform.system() != "Linux",
    reason="exercises Linux executable symlink resolution",
)
def test_resolve_identity_uses_realpath_before_package_lookup(monkeypatch, tmp_path: Path) -> None:
    """A symlinked executable is resolved to its real path before dpkg ownership lookup."""
    backend = LinuxAppInfoBackend()

    target = tmp_path / "python3.12"
    target.write_bytes(b"")
    symlink = tmp_path / "python3"
    symlink.symlink_to(target)

    seen_paths: list[str] = []

    def record_and_reject(path: str) -> None:
        seen_paths.append(path)
        return None

    monkeypatch.setattr(pkg_info, "find_owning_package", record_and_reject)

    backend.resolve_identity(str(symlink))

    assert seen_paths == [os.path.realpath(str(symlink))]
    assert seen_paths[0] != str(symlink)


# --- LinuxAppInfoBackend.resolve_verification(): expensive, deferred, orchestration ---


def _identity(*, name: str = "curl", creator: str = "Unknown") -> ApplicationMetadata:
    """Return a minimal deferred identity result, as resolve_identity() would produce."""
    return ApplicationMetadata(
        name=name,
        creator=creator,
        verification_status=None,
        signature_state=None,
        signature_state_details=None,
    )


def test_resolve_verification_repo_backed_verified_package_is_verified(monkeypatch) -> None:
    """Ownership, clean integrity, and repo provenance together yield PackageVerified/VERIFIED."""
    backend = LinuxAppInfoBackend()

    monkeypatch.setattr(pkg_info, "find_owning_package", lambda path: "curl")
    monkeypatch.setattr(pkg_info, "verify_package_integrity", lambda package, real_path: True)
    monkeypatch.setattr(pkg_info, "is_repo_backed", lambda package: True)

    metadata = backend.resolve_verification("/usr/bin/curl", _identity())

    assert metadata.name == "curl"
    assert metadata.creator == "Unknown"
    assert metadata.verification_status == VerificationStatus.VERIFIED
    assert metadata.signature_state == "PackageVerified"
    assert metadata.signature_state_details is None
    assert humanize_camel_case(metadata.signature_state) == "Package verified"


def test_resolve_verification_locally_installed_deb_is_unknown(monkeypatch) -> None:
    """A package with clean integrity but no configured repo source is UNKNOWN, not VERIFIED."""
    backend = LinuxAppInfoBackend()

    monkeypatch.setattr(pkg_info, "find_owning_package", lambda path: "tapmap")
    monkeypatch.setattr(pkg_info, "verify_package_integrity", lambda package, real_path: True)
    monkeypatch.setattr(pkg_info, "is_repo_backed", lambda package: False)

    metadata = backend.resolve_verification(
        "/usr/bin/tapmap", _identity(name="tapmap", creator="Ola Lie <ola@tip.no>")
    )

    assert metadata.verification_status == VerificationStatus.UNKNOWN
    assert metadata.signature_state == "PackageSourceUnverified"
    assert humanize_camel_case(metadata.signature_state) == "Package source unverified"


def test_resolve_verification_package_modified_fails_verification(monkeypatch) -> None:
    """A package-owned file whose contents no longer match dpkg's record is FAILED."""
    backend = LinuxAppInfoBackend()

    monkeypatch.setattr(pkg_info, "find_owning_package", lambda path: "curl")
    monkeypatch.setattr(pkg_info, "verify_package_integrity", lambda package, real_path: False)

    metadata = backend.resolve_verification("/usr/bin/curl", _identity())

    assert metadata.verification_status == VerificationStatus.FAILED
    assert metadata.signature_state == "PackageModified"
    assert humanize_camel_case(metadata.signature_state) == "Package modified"


def test_resolve_verification_handles_package_removed_between_identity_and_verification(
    monkeypatch,
) -> None:
    """A package removed after resolve_identity() ran resolves to a terminal UNKNOWN, not a crash."""  # noqa: E501
    backend = LinuxAppInfoBackend()

    monkeypatch.setattr(pkg_info, "find_owning_package", lambda path: None)

    metadata = backend.resolve_verification("/usr/bin/curl", _identity())

    assert metadata.verification_status == VerificationStatus.UNKNOWN
    assert metadata.signature_state == "Unpackaged"
    assert metadata.name == "curl"
    assert metadata.creator == "Unknown"


@pytest.mark.skipif(
    platform.system() != "Linux",
    reason="exercises Linux executable symlink resolution",
)
def test_resolve_verification_checks_integrity_against_the_resolved_real_path(
    monkeypatch, tmp_path: Path
) -> None:
    """A package-owned symlinked executable's integrity is checked against its real path."""
    backend = LinuxAppInfoBackend()

    target = tmp_path / "curl-3.2.1"
    target.write_bytes(b"")
    symlink = tmp_path / "curl"
    symlink.symlink_to(target)

    seen: list[tuple[str, str]] = []

    def record_and_confirm(package: str, real_path: str) -> bool:
        seen.append((package, real_path))
        return True

    monkeypatch.setattr(pkg_info, "find_owning_package", lambda path: "curl")
    monkeypatch.setattr(pkg_info, "verify_package_integrity", record_and_confirm)
    monkeypatch.setattr(pkg_info, "is_repo_backed", lambda package: True)

    backend.resolve_verification(str(symlink), _identity())

    assert seen == [("curl", os.path.realpath(str(symlink)))]
