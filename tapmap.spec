# -*- mode: python ; coding: utf-8 -*-
import sys
from tools.build_common import get_signing_identity

a = Analysis(
    ['src/tapmap/__main__.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('src/tapmap/assets', 'tapmap/assets'),
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
    app_icon = "src/tapmap/assets/tapmap.icns"

    kwargs = {}

    if signing_identity := get_signing_identity():
        kwargs["codesign_identity"] = signing_identity

    exe = EXE(
        pyz,
        a.scripts,
        exclude_binaries=True,
        name="tapmap",
        icon=app_icon,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=True,
        **kwargs,
    )
else:
    app_icon = "src/tapmap/assets/tapmap.ico"
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="tapmap",
        icon=app_icon,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=True,
    )

if sys.platform == "darwin":
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        name="tapmap",
    )

    app = BUNDLE(
        coll,
        name="TapMap.app",
        icon=app_icon,
        bundle_identifier=None,
    )
