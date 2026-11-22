# -*- mode: python ; coding: utf-8 -*-
import platform
import sys
from pathlib import Path

from tools.build_common import get_signing_identity, project_metadata

VERSION_FILE = Path("tools") / "windows" / "file_version_info.txt"
MACOS_X86_64_ENTITLEMENTS_FILE = Path("tools") / "macos" / "entitlements-x86_64.plist"
LINUX_LIBRARY_PATH_HOOK = Path("tools") / "linux" / "pyi_rth_library_path.py"

project = project_metadata()
version = project["version"]

datas = [
    ("src/tapmap/assets", "tapmap/assets"),
]

if sys.platform == "win32":
    datas.append(
        (
            "third_party/microsoft_security_extensions",
            "third_party/microsoft_security_extensions",
        )
    )

hiddenimports = []
runtime_hooks = []

if sys.platform == "linux":
    # gi.overrides.* supplies pystray's AppIndicator/GTK backend with
    # convenience members (e.g. GObject.idle_add) through a dynamic
    # mechanism PyInstaller's static import scanner cannot see.
    hiddenimports += [
        "gi.overrides.GLib",
        "gi.overrides.GObject",
        "gi.overrides.Gtk",
        "gi.overrides.Gio",
    ]
    runtime_hooks.append(str(LINUX_LIBRARY_PATH_HOOK))

a = Analysis(
    ["src/tapmap/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=runtime_hooks,
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

if sys.platform == "win32":
    exe_kwargs["version"] = str(VERSION_FILE)

if sys.platform == "darwin":
    if signing_identity := get_signing_identity():
        exe_kwargs["codesign_identity"] = signing_identity
        # Allow executable memory for PyObjC callbacks on signed Intel builds.
        if platform.machine() == "x86_64":
            exe_kwargs["entitlements_file"] = str(MACOS_X86_64_ENTITLEMENTS_FILE)

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
        bundle_identifier="no.tip.tapmap",
        version=version,
        info_plist={
            "CFBundleVersion": version,
            "LSUIElement": True,
        },
    )
