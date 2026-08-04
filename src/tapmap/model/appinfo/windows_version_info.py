"""VERSIONINFO resource reader.

Reads Product Name / Company Name / File Description via the Win32
version.dll API.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

_version = ctypes.WinDLL("version.dll")

_version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
_version.GetFileVersionInfoSizeW.argtypes = [
    wintypes.LPCWSTR,
    ctypes.POINTER(wintypes.DWORD),
]

_version.GetFileVersionInfoW.restype = wintypes.BOOL
_version.GetFileVersionInfoW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPVOID,
]

_version.VerQueryValueW.restype = wintypes.BOOL
_version.VerQueryValueW.argtypes = [
    wintypes.LPVOID,
    wintypes.LPCWSTR,
    ctypes.POINTER(wintypes.LPVOID),
    ctypes.POINTER(wintypes.UINT),
]


class _LANGANDCODEPAGE(ctypes.Structure):
    _fields_ = [("wLanguage", ctypes.c_ushort), ("wCodePage", ctypes.c_ushort)]


def get_version_info(path: str) -> dict[str, str | None]:
    """Return {ProductName, CompanyName, FileDescription} -> str or None."""
    size = _version.GetFileVersionInfoSizeW(path, None)
    if not size:
        return {}

    buf = ctypes.create_string_buffer(size)
    if not _version.GetFileVersionInfoW(path, 0, size, buf):
        return {}

    ptr = wintypes.LPVOID()
    length = wintypes.UINT()
    if not _version.VerQueryValueW(
        buf, r"\VarFileInfo\Translation", ctypes.byref(ptr), ctypes.byref(length)
    ):
        return {}

    # Fields live under a language/codepage-specific block; read the first
    # translation the file declares rather than assuming en-US/Unicode.
    lang_cp = ctypes.cast(ptr, ctypes.POINTER(_LANGANDCODEPAGE))[0]
    prefix = f"\\StringFileInfo\\{lang_cp.wLanguage:04x}{lang_cp.wCodePage:04x}\\"

    fields: dict[str, str | None] = {}
    for name in ("ProductName", "CompanyName", "FileDescription"):
        if _version.VerQueryValueW(
            buf, prefix + name, ctypes.byref(ptr), ctypes.byref(length)
        ):
            fields[name] = ctypes.wstring_at(ptr)
        else:
            fields[name] = None
    return fields
