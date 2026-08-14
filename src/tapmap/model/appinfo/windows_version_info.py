"""VERSIONINFO resource reader.

Reads Product Name / Company Name / File Description via the Win32
version.dll API.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Any

_version: Any = None


class _LANGANDCODEPAGE(ctypes.Structure):
    _fields_ = [("wLanguage", ctypes.c_ushort), ("wCodePage", ctypes.c_ushort)]


def _load() -> None:
    """Load version.dll and configure its function signatures.

    Safe to call more than once; only the first call has any effect.
    """
    global _version

    if _version is not None:
        return

    version = ctypes.WinDLL("version.dll")

    version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    version.GetFileVersionInfoSizeW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]

    version.GetFileVersionInfoW.restype = wintypes.BOOL
    version.GetFileVersionInfoW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
    ]

    version.VerQueryValueW.restype = wintypes.BOOL
    version.VerQueryValueW.argtypes = [
        wintypes.LPVOID,
        wintypes.LPCWSTR,
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.UINT),
    ]

    _version = version


def get_version_info(path: str) -> dict[str, str | None]:
    """Return {ProductName, CompanyName, FileDescription} -> str or None."""
    _load()

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
