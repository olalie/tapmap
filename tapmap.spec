# -*- mode: python ; coding: utf-8 -*-

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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='tapmap',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
