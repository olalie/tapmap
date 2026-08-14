"""Test macOS Mach-O detection and codesign/spctl output parsing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tapmap.model.appinfo import macos_signature_info as sig_info

# --- is_macho ---


def test_is_macho_true_for_64_bit_magic(tmp_path: Path) -> None:
    """A file starting with the 64-bit Mach-O magic number is detected."""
    path = tmp_path / "bin"
    path.write_bytes(b"\xcf\xfa\xed\xfe" + b"\x00" * 12)

    assert sig_info.is_macho(str(path)) is True


def test_is_macho_false_for_shell_script(tmp_path: Path) -> None:
    """A plain text shell script is not a Mach-O."""
    path = tmp_path / "script"
    path.write_bytes(b"#!/bin/bash\necho hi\n")

    assert sig_info.is_macho(str(path)) is False


def test_is_macho_none_when_file_is_unreadable(tmp_path: Path) -> None:
    """A missing file returns None (couldn't determine), not False."""
    assert sig_info.is_macho(str(tmp_path / "does_not_exist")) is None


# --- check_signature: parsing real codesign output (mocked subprocess) ---


class _CompletedProcess:
    """Minimal stand-in for subprocess.CompletedProcess."""

    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _dispatching_run(responses: dict[str, _CompletedProcess]):
    """Return a fake subprocess.run dispatching on 'argv[0] argv[1]' (e.g. 'codesign -dvv')."""

    def run(args: list[str], **kwargs: Any) -> _CompletedProcess:
        return responses[" ".join(args[:2])]

    return run


# Real -dvv output captured against Safari.
_APPLE_SYSTEM_DVV = (
    "Executable=/Applications/Safari.app/Contents/MacOS/Safari\n"
    "Identifier=com.apple.Safari\n"
    "Format=app bundle with Mach-O universal (x86_64 arm64e)\n"
    "Authority=Software Signing\n"
    "Authority=Apple Code Signing Certification Authority\n"
    "Authority=Apple Root CA\n"
    "TeamIdentifier=not set\n"
)

# Real -dvv output captured against TapMap.app.
_DEVELOPER_SIGNED_DVV = (
    "Executable=/Applications/TapMap.app/Contents/MacOS/TapMap\n"
    "Identifier=no.tip.tapmap\n"
    "Format=app bundle with Mach-O thin (arm64)\n"
    "Authority=Developer ID Application: Tip Teknologi i Praksis AS (FUV73783MZ)\n"
    "Authority=Developer ID Certification Authority\n"
    "Authority=Apple Root CA\n"
    "TeamIdentifier=FUV73783MZ\n"
)

# Real -dvv output captured against Keynote.app.
_APP_STORE_DVV = (
    "Executable=/Applications/Keynote.app/Contents/MacOS/Keynote\n"
    "Identifier=com.apple.iWork.Keynote\n"
    "Format=app bundle with Mach-O universal (x86_64 arm64e)\n"
    "Authority=Apple Mac OS Application Signing\n"
    "Authority=Apple Worldwide Developer Relations Certification Authority\n"
    "Authority=Apple Root CA\n"
    "TeamIdentifier=74J34U3R6X\n"
)

# Real -dvv output captured against a locally cc-compiled, ad-hoc signed binary.
_ADHOC_DVV = (
    "Executable=/private/tmp/hello_adhoc\n"
    "Identifier=hello_adhoc\n"
    "Format=Mach-O thin (arm64)\n"
    "CodeDirectory v=20400 size=388 flags=0x20002(adhoc,linker-signed) hashes=9+0 "
    "location=embedded\n"
    "Signature=adhoc\n"
    "TeamIdentifier=not set\n"
)


def test_check_signature_apple_system(monkeypatch) -> None:
    """A Software Signing authority chain maps to AppleSystem with publisher Apple."""
    monkeypatch.setattr(
        sig_info.subprocess,
        "run",
        _dispatching_run(
            {
                "codesign -dvv": _CompletedProcess(0, stderr=_APPLE_SYSTEM_DVV),
                "codesign --verify": _CompletedProcess(0),
            }
        ),
    )

    state, details, publisher = sig_info.check_signature("/Applications/Safari.app")

    assert state == "AppleSystem"
    assert details is None
    assert publisher == "Apple"


def test_check_signature_developer_signed(monkeypatch) -> None:
    """A Developer ID Application authority chain maps to DeveloperSigned."""
    monkeypatch.setattr(
        sig_info.subprocess,
        "run",
        _dispatching_run(
            {
                "codesign -dvv": _CompletedProcess(0, stderr=_DEVELOPER_SIGNED_DVV),
                "codesign --verify": _CompletedProcess(0),
            }
        ),
    )

    state, details, publisher = sig_info.check_signature("/Applications/TapMap.app")

    assert state == "DeveloperSigned"
    assert details is None
    assert publisher == "Tip Teknologi i Praksis AS"


def test_check_signature_app_store_signed(monkeypatch) -> None:
    """An Apple Mac OS Application Signing authority chain maps to AppStoreSigned."""
    monkeypatch.setattr(
        sig_info.subprocess,
        "run",
        _dispatching_run(
            {
                "codesign -dvv": _CompletedProcess(0, stderr=_APP_STORE_DVV),
                "codesign --verify": _CompletedProcess(0),
            }
        ),
    )

    state, details, publisher = sig_info.check_signature("/Applications/Keynote.app")

    assert state == "AppStoreSigned"
    assert details is None
    assert publisher is None


def test_check_signature_adhoc(monkeypatch) -> None:
    """No Authority chain, but a valid signature, maps to AdHoc with no publisher."""
    monkeypatch.setattr(
        sig_info.subprocess,
        "run",
        _dispatching_run(
            {
                "codesign -dvv": _CompletedProcess(0, stderr=_ADHOC_DVV),
                "codesign --verify": _CompletedProcess(0),
            }
        ),
    )

    state, details, publisher = sig_info.check_signature("/tmp/hello_adhoc")

    assert state == "AdHoc"
    assert details is None
    assert publisher is None


def test_check_signature_unsigned(monkeypatch) -> None:
    """Codesign's 'not signed at all' message maps to Unsigned."""
    monkeypatch.setattr(
        sig_info.subprocess,
        "run",
        _dispatching_run(
            {
                "codesign -dvv": _CompletedProcess(
                    1, stderr="/tmp/hello_stripped: code object is not signed at all\n"
                ),
            }
        ),
    )

    state, details, publisher = sig_info.check_signature("/tmp/hello_stripped")

    assert state == "Unsigned"
    assert details is None
    assert publisher is None


def test_check_signature_invalid_carries_verify_diagnostic(monkeypatch) -> None:
    """A tampered signature maps to Invalid, with codesign's own diagnostic as details."""
    monkeypatch.setattr(
        sig_info.subprocess,
        "run",
        _dispatching_run(
            {
                "codesign -dvv": _CompletedProcess(0, stderr=_ADHOC_DVV),
                "codesign --verify": _CompletedProcess(
                    1,
                    stderr=(
                        "/tmp/hello_tamper: invalid signature (code or signature have "
                        "been modified)\nIn architecture: arm64\n"
                    ),
                ),
            }
        ),
    )

    state, details, publisher = sig_info.check_signature("/tmp/hello_tamper")

    assert state == "Invalid"
    assert details == "invalid signature (code or signature have been modified)"
    assert publisher is None


def _run_with_unrecognized_error(args: list[str], **kwargs: Any) -> _CompletedProcess:
    return _CompletedProcess(1, stderr="unrecognized codesign error\n")


def _run_raising_oserror(args: list[str], **kwargs: Any) -> _CompletedProcess:
    raise OSError("codesign not found")


def _run_raising_decode_error(args: list[str], **kwargs: Any) -> _CompletedProcess:
    raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")


@pytest.mark.parametrize(
    "run",
    [
        pytest.param(_run_with_unrecognized_error, id="unrecognized-error-text"),
        pytest.param(_run_raising_oserror, id="codesign-missing"),
        pytest.param(_run_raising_decode_error, id="undecodable-output"),
    ],
)
def test_check_signature_unexpected_failure_returns_all_none(monkeypatch, run) -> None:
    """Any unexpected codesign failure is UNKNOWN-shaped, not a false negative."""
    monkeypatch.setattr(sig_info.subprocess, "run", run)

    assert sig_info.check_signature("/tmp/whatever") == (None, None, None)


# --- check_notarized ---


def test_check_notarized_true_when_source_confirms(monkeypatch) -> None:
    """Spctl reporting 'Notarized Developer ID' confirms notarization."""
    monkeypatch.setattr(
        sig_info.subprocess,
        "run",
        _dispatching_run(
            {
                "spctl -a": _CompletedProcess(
                    0,
                    stderr=(
                        "/Applications/TapMap.app: accepted\n"
                        "source=Notarized Developer ID\n"
                        "origin=Developer ID Application: Tip Teknologi i Praksis AS "
                        "(FUV73783MZ)\n"
                    ),
                ),
            }
        ),
    )

    assert sig_info.check_notarized("/Applications/TapMap.app") is True


def test_check_notarized_false_when_spctl_cannot_assess_bare_executable(monkeypatch) -> None:
    """Spctl rejecting a bare executable (not an app) does not confirm notarization."""
    monkeypatch.setattr(
        sig_info.subprocess,
        "run",
        _dispatching_run(
            {
                "spctl -a": _CompletedProcess(
                    3,
                    stderr=(
                        "/venv/bin/python3: rejected (the code is valid but does not "
                        "seem to be an app)\n"
                        "origin=Developer ID Application: Python Software Foundation "
                        "(BMM5U3QVKW)\n"
                    ),
                ),
            }
        ),
    )

    assert sig_info.check_notarized("/venv/bin/python3") is False
