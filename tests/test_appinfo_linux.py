"""Test the Linux AppInfo backend: name resolution, trust mapping, and orchestration."""

from __future__ import annotations

import os
from pathlib import Path

from tapmap.model.appinfo import TrustVerdict
from tapmap.model.appinfo import linux_package_info as pkg_info
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


# --- LinuxAppInfoBackend.resolve(): orchestration (data sources mocked) ---


def test_resolve_repo_backed_verified_package_is_trusted(monkeypatch) -> None:
    """Ownership, clean integrity, and repo provenance together yield PackageVerified/TRUSTED."""
    backend = LinuxAppInfoBackend()

    monkeypatch.setattr(pkg_info, "find_owning_package", lambda path: "curl")
    monkeypatch.setattr(pkg_info, "find_desktop_name", lambda package: None)
    monkeypatch.setattr(pkg_info, "find_creator", lambda package: None)
    monkeypatch.setattr(pkg_info, "verify_package_integrity", lambda package, real_path: True)
    monkeypatch.setattr(pkg_info, "is_repo_backed", lambda package: True)

    metadata = backend.resolve("/usr/bin/curl")

    assert metadata.name == "curl"
    assert metadata.creator == "Unknown"
    assert metadata.trust == TrustVerdict.TRUSTED
    assert metadata.signature_state == "PackageVerified"
    assert metadata.signature_state_details is None
    assert humanize_camel_case(metadata.signature_state) == "Package verified"


def test_resolve_locally_installed_deb_is_unknown(monkeypatch) -> None:
    """A package with clean integrity but no configured repo source is UNKNOWN, not TRUSTED."""
    backend = LinuxAppInfoBackend()

    monkeypatch.setattr(pkg_info, "find_owning_package", lambda path: "tapmap")
    monkeypatch.setattr(pkg_info, "find_desktop_name", lambda package: None)
    monkeypatch.setattr(pkg_info, "find_creator", lambda package: "Ola Lie <ola@tip.no>")
    monkeypatch.setattr(pkg_info, "verify_package_integrity", lambda package, real_path: True)
    monkeypatch.setattr(pkg_info, "is_repo_backed", lambda package: False)

    metadata = backend.resolve("/usr/bin/tapmap")

    assert metadata.trust == TrustVerdict.UNKNOWN
    assert metadata.signature_state == "PackageSourceUnverified"
    assert humanize_camel_case(metadata.signature_state) == "Package source unverified"


def test_resolve_package_modified_is_not_trusted(monkeypatch) -> None:
    """A package-owned file whose contents no longer match dpkg's record is NOT_TRUSTED."""
    backend = LinuxAppInfoBackend()

    monkeypatch.setattr(pkg_info, "find_owning_package", lambda path: "curl")
    monkeypatch.setattr(pkg_info, "find_desktop_name", lambda package: None)
    monkeypatch.setattr(pkg_info, "find_creator", lambda package: None)
    monkeypatch.setattr(pkg_info, "verify_package_integrity", lambda package, real_path: False)

    metadata = backend.resolve("/usr/bin/curl")

    assert metadata.trust == TrustVerdict.NOT_TRUSTED
    assert metadata.signature_state == "PackageModified"
    assert humanize_camel_case(metadata.signature_state) == "Package modified"


def test_resolve_unpackaged_executable_is_unknown(monkeypatch) -> None:
    """An executable owned by no dpkg package is UNKNOWN."""
    backend = LinuxAppInfoBackend()

    monkeypatch.setattr(pkg_info, "find_owning_package", lambda path: None)

    metadata = backend.resolve("/snap/firefox/current/usr/lib/firefox/firefox")

    assert metadata.name == "firefox"
    assert metadata.creator == "Unknown"
    assert metadata.trust == TrustVerdict.UNKNOWN
    assert metadata.signature_state == "Unpackaged"
    assert humanize_camel_case(metadata.signature_state) == "Unpackaged"


def test_resolve_uses_realpath_before_package_lookup(monkeypatch, tmp_path: Path) -> None:
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

    backend.resolve(str(symlink))

    assert seen_paths == [os.path.realpath(str(symlink))]
    assert seen_paths[0] != str(symlink)


def test_resolve_checks_integrity_against_the_resolved_real_path(
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
    monkeypatch.setattr(pkg_info, "find_desktop_name", lambda package: None)
    monkeypatch.setattr(pkg_info, "find_creator", lambda package: None)
    monkeypatch.setattr(pkg_info, "verify_package_integrity", record_and_confirm)
    monkeypatch.setattr(pkg_info, "is_repo_backed", lambda package: True)

    backend.resolve(str(symlink))

    assert seen == [("curl", os.path.realpath(str(symlink)))]


def test_resolve_creator_omits_generic_ubuntu_maintainer(monkeypatch) -> None:
    """A generic distribution maintainer resolves to an unknown creator."""
    backend = LinuxAppInfoBackend()

    monkeypatch.setattr(pkg_info, "find_owning_package", lambda path: "curl")
    monkeypatch.setattr(pkg_info, "find_desktop_name", lambda package: None)
    monkeypatch.setattr(pkg_info, "find_creator", lambda package: None)
    monkeypatch.setattr(pkg_info, "verify_package_integrity", lambda package, real_path: True)
    monkeypatch.setattr(pkg_info, "is_repo_backed", lambda package: True)

    metadata = backend.resolve("/usr/bin/curl")

    assert metadata.creator == "Unknown"
