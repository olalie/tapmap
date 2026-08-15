"""Test dpkg/apt package provenance lookups (mocked subprocess)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tapmap.model.appinfo import linux_package_info as pkg_info

# --- find_owning_package ---


class _CompletedProcess:
    """Minimal stand-in for subprocess.CompletedProcess."""

    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _dispatching_run(responses: dict[str, _CompletedProcess]):
    """Return a fake subprocess.run dispatching on 'argv[0] argv[1]' (e.g. 'dpkg -S')."""

    def run(args: list[str], **kwargs: Any) -> _CompletedProcess:
        return responses[" ".join(args[:2])]

    return run


def test_find_owning_package_parses_real_dpkg_s_output(monkeypatch) -> None:
    """A real 'dpkg -S' single-owner line resolves to the package name."""
    monkeypatch.setattr(
        pkg_info.subprocess,
        "run",
        _dispatching_run({"dpkg -S": _CompletedProcess(0, stdout="curl: /usr/bin/curl\n")}),
    )

    assert pkg_info.find_owning_package("/usr/bin/curl") == "curl"


def test_find_owning_package_none_when_unowned(monkeypatch) -> None:
    """A path dpkg doesn't recognize returns None."""
    monkeypatch.setattr(
        pkg_info.subprocess,
        "run",
        _dispatching_run(
            {
                "dpkg -S": _CompletedProcess(
                    1, stderr="dpkg-query: no path found matching pattern\n"
                )
            }
        ),
    )

    assert pkg_info.find_owning_package("/opt/local/bin/tool") is None


def test_find_owning_package_none_when_dpkg_missing(monkeypatch) -> None:
    """A missing dpkg binary returns None, not raising."""

    def raise_oserror(args: list[str], **kwargs: Any) -> _CompletedProcess:
        raise OSError("dpkg not found")

    monkeypatch.setattr(pkg_info.subprocess, "run", raise_oserror)

    assert pkg_info.find_owning_package("/usr/bin/curl") is None


# --- verify_package_integrity ---


def test_verify_package_integrity_true_when_dpkg_v_clean(monkeypatch) -> None:
    """A clean 'dpkg -V' (no output, exit 0) verifies the executable as intact."""
    monkeypatch.setattr(
        pkg_info.subprocess, "run", _dispatching_run({"dpkg -V": _CompletedProcess(0)})
    )

    assert pkg_info.verify_package_integrity("curl", "/usr/bin/curl") is True


def test_verify_package_integrity_false_when_the_executable_itself_is_flagged(
    monkeypatch,
) -> None:
    """A checksum mismatch reported for the executable's own path verifies as modified."""
    monkeypatch.setattr(
        pkg_info.subprocess,
        "run",
        _dispatching_run(
            {"dpkg -V": _CompletedProcess(0, stdout="??5??????   /usr/bin/curl\n")}
        ),
    )

    assert pkg_info.verify_package_integrity("curl", "/usr/bin/curl") is False


def test_verify_package_integrity_true_when_only_another_package_file_is_flagged(
    monkeypatch,
) -> None:
    """A mismatch reported for a different file in the same package doesn't flag the exe."""
    monkeypatch.setattr(
        pkg_info.subprocess,
        "run",
        _dispatching_run(
            {
                "dpkg -V": _CompletedProcess(
                    0,
                    stdout=(
                        "??5?????? c /etc/curl/curlrc\n??5??????   /usr/share/doc/curl/x\n"
                    ),
                )
            }
        ),
    )

    assert pkg_info.verify_package_integrity("curl", "/usr/bin/curl") is True


def test_verify_package_integrity_false_when_executable_is_missing(monkeypatch) -> None:
    """A 'missing' entry for the executable's own path verifies as modified, not skipped."""
    monkeypatch.setattr(
        pkg_info.subprocess,
        "run",
        _dispatching_run(
            {
                "dpkg -V": _CompletedProcess(
                    0, stdout="missing   /usr/bin/curl (No such file or directory)\n"
                )
            }
        ),
    )

    assert pkg_info.verify_package_integrity("curl", "/usr/bin/curl") is False


def test_verify_package_integrity_false_when_dpkg_missing(monkeypatch) -> None:
    """A missing dpkg binary returns False, not raising and not treated as intact."""

    def raise_oserror(args: list[str], **kwargs: Any) -> _CompletedProcess:
        raise OSError("dpkg not found")

    monkeypatch.setattr(pkg_info.subprocess, "run", raise_oserror)

    assert pkg_info.verify_package_integrity("curl", "/usr/bin/curl") is False


def test_verify_package_integrity_false_when_dpkg_v_fails_without_flagging_a_path(
    monkeypatch,
) -> None:
    """A nonzero exit with nothing flagged (e.g. the package vanished) is a failed check."""
    monkeypatch.setattr(
        pkg_info.subprocess,
        "run",
        _dispatching_run(
            {
                "dpkg -V": _CompletedProcess(
                    1, stderr="dpkg: package 'curl' is not installed\n"
                )
            }
        ),
    )

    assert pkg_info.verify_package_integrity("curl", "/usr/bin/curl") is False


# --- is_repo_backed: parsing real apt-cache policy output ---

# Real apt-cache policy output captured against curl.
_REPO_BACKED_POLICY = """curl:
  Installed: 8.5.0-2ubuntu10.11
  Candidate: 8.5.0-2ubuntu10.11
  Version table:
 *** 8.5.0-2ubuntu10.11 500
        500 http://archive.ubuntu.com/ubuntu noble-updates/main amd64 Packages
        500 http://security.ubuntu.com/ubuntu noble-security/main amd64 Packages
        100 /var/lib/dpkg/status
     8.5.0-2ubuntu10 500
        500 http://archive.ubuntu.com/ubuntu noble/main amd64 Packages
"""

# Real apt-cache policy output captured against tapmap (installed via dpkg -i, not from a repo).
_LOCALLY_INSTALLED_POLICY = """tapmap:
  Installed: 1.9.0
  Candidate: 1.9.0
  Version table:
 *** 1.9.0 100
        100 /var/lib/dpkg/status
"""


def test_is_repo_backed_true_for_archive_installed_package(monkeypatch) -> None:
    """A package whose installed version has a real repo URL is repo-backed."""
    monkeypatch.setattr(
        pkg_info.subprocess,
        "run",
        _dispatching_run(
            {"apt-cache policy": _CompletedProcess(0, stdout=_REPO_BACKED_POLICY)}
        ),
    )

    assert pkg_info.is_repo_backed("curl") is True


def test_is_repo_backed_false_for_locally_installed_deb(monkeypatch) -> None:
    """A side-loaded package with only '/var/lib/dpkg/status' as its source is not repo-backed."""
    monkeypatch.setattr(
        pkg_info.subprocess,
        "run",
        _dispatching_run(
            {"apt-cache policy": _CompletedProcess(0, stdout=_LOCALLY_INSTALLED_POLICY)}
        ),
    )

    assert pkg_info.is_repo_backed("tapmap") is False


def test_is_repo_backed_false_when_apt_cache_missing(monkeypatch) -> None:
    """A missing apt-cache binary returns False, not raising."""

    def raise_oserror(args: list[str], **kwargs: Any) -> _CompletedProcess:
        raise OSError("apt-cache not found")

    monkeypatch.setattr(pkg_info.subprocess, "run", raise_oserror)

    assert pkg_info.is_repo_backed("curl") is False


# --- find_creator ---


def test_find_creator_returns_real_maintainer(monkeypatch) -> None:
    """A package-specific maintainer is returned as-is."""
    monkeypatch.setattr(
        pkg_info.subprocess,
        "run",
        _dispatching_run(
            {"dpkg-query -W": _CompletedProcess(0, stdout="Ola Lie <ola@tip.no>")}
        ),
    )

    assert pkg_info.find_creator("tapmap") == "Ola Lie <ola@tip.no>"


def test_find_creator_none_for_generic_ubuntu_developers(monkeypatch) -> None:
    """'Ubuntu Developers' is a distro packaging team, not the application's creator."""
    monkeypatch.setattr(
        pkg_info.subprocess,
        "run",
        _dispatching_run(
            {
                "dpkg-query -W": _CompletedProcess(
                    0, stdout="Ubuntu Developers <ubuntu-devel-discuss@lists.ubuntu.com>"
                )
            }
        ),
    )

    assert pkg_info.find_creator("curl") is None


def test_find_creator_none_for_generic_ubuntu_core_developers(monkeypatch) -> None:
    """'Ubuntu Core Developers' is also a distro packaging team, not a creator."""
    monkeypatch.setattr(
        pkg_info.subprocess,
        "run",
        _dispatching_run(
            {
                "dpkg-query -W": _CompletedProcess(
                    0, stdout="Ubuntu Core Developers <ubuntu-devel-discuss@lists.ubuntu.com>"
                )
            }
        ),
    )

    assert pkg_info.find_creator("python3.12-minimal") is None


def test_find_creator_none_when_dpkg_query_fails(monkeypatch) -> None:
    """A failed dpkg-query lookup returns None."""
    monkeypatch.setattr(
        pkg_info.subprocess, "run", _dispatching_run({"dpkg-query -W": _CompletedProcess(1)})
    )

    assert pkg_info.find_creator("curl") is None


# --- _package_desktop_files ---


def test_package_desktop_files_filters_dpkg_l_output(monkeypatch) -> None:
    """Only .desktop files under /usr/share/applications/ are kept from dpkg -L's file list."""
    dpkg_l_output = (
        "/usr/share/applications\n"
        "/usr/share/applications/editorapp.desktop\n"
        "/usr/share/applications/mimeinfo.cache\n"
        "/usr/bin/editorapp\n"
        "/usr/share/doc/editorapp/changelog.gz\n"
        "/usr/share/man/man1/editorapp.1.gz\n"
    )
    seen_args: list[list[str]] = []

    def record_and_respond(args: list[str], **kwargs: Any) -> _CompletedProcess:
        seen_args.append(args)
        return _CompletedProcess(0, stdout=dpkg_l_output)

    monkeypatch.setattr(pkg_info.subprocess, "run", record_and_respond)

    assert pkg_info._package_desktop_files("editorapp") == [
        "/usr/share/applications/editorapp.desktop"
    ]
    assert seen_args == [["dpkg", "-L", "editorapp"]]


# --- find_desktop_name ---


def test_find_desktop_name_uses_the_one_visible_entry(monkeypatch, tmp_path: Path) -> None:
    """A package's single visible .desktop entry supplies the display name."""
    desktop = tmp_path / "code.desktop"
    desktop.write_text("[Desktop Entry]\nName=Visual Studio Code\nType=Application\n")

    monkeypatch.setattr(
        pkg_info,
        "_package_desktop_files",
        lambda package: [str(desktop)],
    )

    assert pkg_info.find_desktop_name("code") == "Visual Studio Code"


def test_find_desktop_name_ignores_nodisplay_entries(monkeypatch, tmp_path: Path) -> None:
    """A package owning both a visible entry and a NoDisplay helper entry still resolves."""
    visible = tmp_path / "code.desktop"
    visible.write_text("[Desktop Entry]\nName=Visual Studio Code\nType=Application\n")
    hidden = tmp_path / "code-url-handler.desktop"
    hidden.write_text(
        "[Desktop Entry]\nName=Visual Studio Code - URL Handler\nNoDisplay=true\n"
    )

    monkeypatch.setattr(
        pkg_info,
        "_package_desktop_files",
        lambda package: [str(hidden), str(visible)],
    )

    assert pkg_info.find_desktop_name("code") == "Visual Studio Code"


def test_find_desktop_name_none_when_ambiguous(monkeypatch, tmp_path: Path) -> None:
    """Multiple visible .desktop entries return None."""
    first = tmp_path / "a.desktop"
    first.write_text("[Desktop Entry]\nName=A\n")
    second = tmp_path / "b.desktop"
    second.write_text("[Desktop Entry]\nName=B\n")

    monkeypatch.setattr(
        pkg_info,
        "_package_desktop_files",
        lambda package: [str(first), str(second)],
    )

    assert pkg_info.find_desktop_name("ambiguous-pkg") is None


def test_find_desktop_name_none_when_package_has_no_desktop_file(monkeypatch) -> None:
    """A package that owns no .desktop file (e.g. a CLI tool) returns None."""
    monkeypatch.setattr(pkg_info, "_package_desktop_files", lambda package: [])

    assert pkg_info.find_desktop_name("curl") is None
