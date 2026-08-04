"""Signature status via Microsoft.Security.Extensions.FileSignatureInfo.

Understands both embedded Authenticode signatures and catalog signatures
(the mechanism most Windows system binaries use instead of an embedded
signature).

Loading the wrapper DLL embeds the .NET runtime into the process (via
pythonnet) on first use; this cannot be undone or reloaded with a different
path, so load() is meant to be called exactly once, at AppInfo construction.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_FileSignatureInfo: Any = None
_File: Any = None
_X509NameType: Any = None


def load(dll_dir: Path) -> None:
    """Load the Microsoft.Security.Extensions wrapper DLL from dll_dir.

    Safe to call more than once; only the first call has any effect.

    Raises:
        Exception: on any failure to load the CLR wrapper. Callers are
            responsible for catching this and degrading gracefully.
    """
    global _FileSignatureInfo, _File, _X509NameType

    if _FileSignatureInfo is not None:
        return

    dll_path = Path(dll_dir) / "getfilesiginforedistwrapper.dll"
    if not dll_path.is_file():
        raise FileNotFoundError(dll_path)

    import clr

    clr.AddReference(str(dll_path))

    from Microsoft.Security.Extensions import FileSignatureInfo
    from System.IO import File
    from System.Security.Cryptography.X509Certificates import X509NameType

    _FileSignatureInfo = FileSignatureInfo
    _File = File
    _X509NameType = X509NameType


def check_signature(path: str) -> tuple[str, str, str | None]:
    """Return (state, state_reason, publisher) for a file.

    state/state_reason are the .NET enum values (Microsoft.Security.Extensions
    .SignatureState / .SignatureStateReason) stringified, e.g. "SignedAndTrusted"
    / "None". publisher is the signing certificate's simple subject name, or
    None if the file has no signing certificate.

    Requires load() to have been called first.
    """
    stream = _File.OpenRead(path)
    try:
        info = _FileSignatureInfo.GetFromFileStream(stream)
    finally:
        stream.Close()

    publisher = None
    if info.SigningCertificate is not None:
        publisher = info.SigningCertificate.GetNameInfo(_X509NameType.SimpleName, False)

    return str(info.State), str(info.StateReason), publisher
