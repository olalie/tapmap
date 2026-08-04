"""WinVerifyTrust fallback for files FileSignatureInfo reports as Unsigned.

Some catalog-signed binaries are not recognized by
Microsoft.Security.Extensions.FileSignatureInfo but are trusted by Windows'
own WinVerifyTrust API. This module resolves exactly that case; it is not a
general-purpose signature checker and is not meant to be called for files
FileSignatureInfo already considers signed.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

_wintrust = ctypes.WinDLL("wintrust.dll")
_crypt32 = ctypes.WinDLL("crypt32.dll")


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


# WINTRUST_ACTION_GENERIC_VERIFY_V2 - fixed GUID identifying "verify as a
# signed file" to WinVerifyTrust.
_ACTION_GENERIC_VERIFY_V2 = _GUID(
    0x00AAC56B,
    0xCD44,
    0x11D0,
    (ctypes.c_ubyte * 8)(0x8C, 0xC2, 0x00, 0xC0, 0x4F, 0xC2, 0x95, 0xEE),
)


class _WINTRUST_FILE_INFO(ctypes.Structure):
    _fields_ = [
        ("cbStruct", wintypes.DWORD),
        ("pcwszFilePath", wintypes.LPCWSTR),
        ("hFile", wintypes.HANDLE),
        ("pgKnownSubject", ctypes.c_void_p),
    ]


class _WINTRUST_DATA(ctypes.Structure):
    _fields_ = [
        ("cbStruct", wintypes.DWORD),
        ("pPolicyCallbackData", ctypes.c_void_p),
        ("pSIPClientData", ctypes.c_void_p),
        ("dwUIChoice", wintypes.DWORD),
        ("fdwRevocationChecks", wintypes.DWORD),
        ("dwUnionChoice", wintypes.DWORD),
        ("pFile", ctypes.POINTER(_WINTRUST_FILE_INFO)),
        ("dwStateAction", wintypes.DWORD),
        ("hWVTStateData", wintypes.HANDLE),
        ("pwszURLReference", wintypes.LPCWSTR),
        ("dwProvFlags", wintypes.DWORD),
        ("dwUIContext", wintypes.DWORD),
        ("pSignatureSettings", ctypes.c_void_p),
    ]


# Only the leading fields are declared - enough to read pCert at its correct
# offset; the real struct has more trailing fields we never touch.
class _CRYPT_PROVIDER_CERT(ctypes.Structure):
    _fields_ = [("cbStruct", wintypes.DWORD), ("pCert", ctypes.c_void_p)]


_WTD_UI_NONE = 2
_WTD_REVOKE_NONE = 0
_WTD_CHOICE_FILE = 1
_WTD_STATEACTION_VERIFY = 1
_WTD_STATEACTION_CLOSE = 2
_CERT_NAME_SIMPLE_DISPLAY_TYPE = 4

_wintrust.WinVerifyTrust.restype = ctypes.c_long
_wintrust.WinVerifyTrust.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(_GUID),
    ctypes.POINTER(_WINTRUST_DATA),
]

_wintrust.WTHelperProvDataFromStateData.restype = ctypes.c_void_p
_wintrust.WTHelperProvDataFromStateData.argtypes = [wintypes.HANDLE]

_wintrust.WTHelperGetProvSignerFromChain.restype = ctypes.c_void_p
_wintrust.WTHelperGetProvSignerFromChain.argtypes = [
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.BOOL,
    wintypes.DWORD,
]

_wintrust.WTHelperGetProvCertFromChain.restype = ctypes.c_void_p
_wintrust.WTHelperGetProvCertFromChain.argtypes = [ctypes.c_void_p, wintypes.DWORD]

_crypt32.CertGetNameStringW.restype = wintypes.DWORD
_crypt32.CertGetNameStringW.argtypes = [
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.LPWSTR,
    wintypes.DWORD,
]


def _get_signer_name(cert_ptr: int) -> str | None:
    size = _crypt32.CertGetNameStringW(
        cert_ptr, _CERT_NAME_SIMPLE_DISPLAY_TYPE, 0, None, None, 0
    )
    if size <= 1:
        return None
    buf = ctypes.create_unicode_buffer(size)
    _crypt32.CertGetNameStringW(
        cert_ptr, _CERT_NAME_SIMPLE_DISPLAY_TYPE, 0, None, buf, size
    )
    return buf.value or None


def check_trust_override(path: str) -> tuple[bool, str | None]:
    """Return (is_trusted, publisher) from WinVerifyTrust for `path`.

    Intended only as a fallback when FileSignatureInfo reports Unsigned.
    """
    file_info = _WINTRUST_FILE_INFO(
        cbStruct=ctypes.sizeof(_WINTRUST_FILE_INFO), pcwszFilePath=path
    )

    data = _WINTRUST_DATA()
    data.cbStruct = ctypes.sizeof(_WINTRUST_DATA)
    data.dwUIChoice = _WTD_UI_NONE
    data.fdwRevocationChecks = _WTD_REVOKE_NONE
    data.dwUnionChoice = _WTD_CHOICE_FILE
    data.pFile = ctypes.pointer(file_info)
    data.dwStateAction = _WTD_STATEACTION_VERIFY

    result = _wintrust.WinVerifyTrust(
        wintypes.HWND(-1), ctypes.byref(_ACTION_GENERIC_VERIFY_V2), ctypes.byref(data)
    )
    is_trusted = result == 0

    publisher = None
    if is_trusted and data.hWVTStateData:
        prov_data = _wintrust.WTHelperProvDataFromStateData(data.hWVTStateData)
        signer = (
            _wintrust.WTHelperGetProvSignerFromChain(prov_data, 0, False, 0)
            if prov_data
            else None
        )
        cert_ptr = (
            _wintrust.WTHelperGetProvCertFromChain(signer, 0) if signer else None
        )
        if cert_ptr:
            prov_cert = ctypes.cast(
                cert_ptr, ctypes.POINTER(_CRYPT_PROVIDER_CERT)
            ).contents
            if prov_cert.pCert:
                publisher = _get_signer_name(prov_cert.pCert)

    # Must close the state, reusing the same WINTRUST_DATA, to release resources.
    data.dwStateAction = _WTD_STATEACTION_CLOSE
    _wintrust.WinVerifyTrust(
        wintypes.HWND(-1), ctypes.byref(_ACTION_GENERIC_VERIFY_V2), ctypes.byref(data)
    )

    return is_trusted, publisher
