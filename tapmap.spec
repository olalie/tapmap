# -*- mode: python ; coding: utf-8 -*-
import sys

from tools.build_common import get_signing_identity

a = Analysis(
    ["src/tapmap/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=[
        ("src/tapmap/assets", "tapmap/assets"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

if sys.platform == "darwin":
    app_name = "TapMap"
    app_icon = "src/tapmap/assets/tapmap.icns"
else:
    app_name = "tapmap"
    app_icon = "src/tapmap/assets/tapmap.ico"

exe_kwargs = {}

if sys.platform == "darwin":
    if signing_identity := get_signing_identity():
        exe_kwargs["codesign_identity"] = signing_identity

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name=app_name,
    icon=app_icon,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    **exe_kwargs,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name=app_name,
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{app_name}.app",
        icon=app_icon,
        bundle_identifier=None,
    )
