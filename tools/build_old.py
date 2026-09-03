"""Build TapMap release artifacts.

Run from project root:

    python tools/build.py

    Current release pipeline
    ------------------------
    1. Clean previous build artifacts.
    2. Build application with PyInstaller.
    3. Create platform-specific release artifacts.

    Future release pipeline
    ------------------------
    4. Code sign release artifacts.
    5. Verify digital signature.
    6. Submit for notarization (macOS).
    7. Staple notarization ticket (macOS).
    8. Verify Gatekeeper acceptance (macOS).
    9. Publish release artifacts.
"""

from __future__ import annotations

import contextlib
import gzip
import os
import shutil
import stat
import subprocess
import sys
import time
import tomllib
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SPEC_FILE = PROJECT_ROOT / "tapmap.spec"

BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"

# Temporary folder used as the DMG source.
# Only files copied here are included in the installer.
PACKAGE_DIR = PROJECT_ROOT / "package"

DMG_DIR = PROJECT_ROOT / "dmg"

MACOS_APP_NAME = "TapMap.app"
MACOS_DMG_NAME = "TapMap.dmg"

DIST_NAME = "tapmap"
EXE_NAME_WINDOWS = "tapmap.exe"


def project_metadata() -> dict:
    """Return project metadata from pyproject.toml."""
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as f:
        return tomllib.load(f)["project"]


# Helpers
def run(cmd: list[str]) -> None:
    """Run a subprocess command."""
    print(">", " ".join(cmd))
    subprocess.run(cmd, check=True)


def stop_running_app() -> None:
    """Terminate a running packaged executable on Windows."""
    if os.name != "nt":
        return

    with contextlib.suppress(Exception):
        subprocess.run(
            ["taskkill", "/F", "/IM", EXE_NAME_WINDOWS],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _on_rm_error(func, path: str, _exc) -> None:
    """Retry removal of read-only files."""
    with contextlib.suppress(Exception):
        os.chmod(path, stat.S_IWRITE)
    func(path)


def rm_tree(path: Path, *, retries: int = 12, delay_s: float = 0.25) -> None:
    """Remove a file or directory tree."""
    if not path.exists():
        return

    last_exc: Exception | None = None

    for _ in range(retries):
        try:
            if path.is_dir():
                shutil.rmtree(path, onexc=_on_rm_error)
            else:
                path.unlink()
            return
        except Exception as exc:
            last_exc = exc
            time.sleep(delay_s)

    if last_exc:
        raise last_exc


def expected_output_file() -> Path:
    """Return expected PyInstaller output."""
    if sys.platform == "darwin":
        return DIST_DIR / MACOS_APP_NAME

    out = DIST_DIR / DIST_NAME

    if os.name == "nt":
        out = out.with_suffix(".exe")

    return out


# Build
def clean() -> None:
    """Remove previous build artifacts."""
    stop_running_app()
    rm_tree(BUILD_DIR)
    rm_tree(DIST_DIR)
    rm_tree(DMG_DIR)
    rm_tree(PACKAGE_DIR)
    print("[OK] Clean build directories")


def build_pyinstaller() -> None:
    """Run PyInstaller."""
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            str(SPEC_FILE),
        ]
    )
    print("[OK] Build application")


def verify_build() -> None:
    """Verify that the expected build output exists."""
    out_file = expected_output_file()

    if not out_file.exists():
        raise FileNotFoundError(f"Expected output not found: {out_file}")

    print(f"[OK] Verify build ({out_file.name})")


# Linux packaging helpers
def write_debian_changelog(doc_dir: Path, project: dict) -> None:
    """Write Debian changelog."""
    author = project["authors"][0]

    changelog = f"""\
{project["name"]} ({project["version"]}) unstable; urgency=medium

  * Release {project["version"]}

 -- {author["name"]} <{author["email"]}>  {format_datetime(datetime.now().astimezone())}
"""

    with gzip.open(
        doc_dir / "changelog.gz",
        "wt",
        encoding="utf-8",
    ) as f:
        f.write(changelog)


def write_debian_control(
    package_dir: Path,
    project: dict,
    depends: str,
) -> None:
    """Write DEBIAN/control."""
    author = project["authors"][0]
    description = project["description"]
    summary, details = description.split(". ", 1)

    (package_dir / "DEBIAN" / "control").write_text(
        f"""Package: {project["name"]}
Version: {project["version"]}
Section: net
Priority: optional
Architecture: amd64
Maintainer: {author["name"]} <{author["email"]}>
Depends: {depends}
Homepage: https://tip.no/tapmap/
Description: {summary}
 {details}
""",
        encoding="utf-8",
    )


def write_desktop_file(package_dir: Path, project: dict) -> None:
    """Write desktop launcher."""
    (package_dir / "usr" / "share" / "applications" / "no.tip.tapmap.desktop").write_text(
        f"""[Desktop Entry]
Type=Application
Name={project["name"]}
Comment={project["description"]}
Exec=tapmap
Icon=tapmap
Terminal=false
Categories=Network;
StartupNotify=true
""",
        encoding="utf-8",
    )


def copy_linux_icons(package_dir: Path, icons_dir: Path) -> None:
    """Install application icons into the standard hicolor icon theme.

    Desktop environments automatically select the most appropriate icon size.
    """
    for icon in icons_dir.glob("tapmap-*.png"):
        size = icon.stem.removeprefix("tapmap-")

        target = package_dir / "usr" / "share" / "icons" / "hicolor" / f"{size}x{size}" / "apps"

        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(icon, target / "tapmap.png")


def install_manual_page(
    package_dir: Path,
    linux_assets_dir: Path,
) -> None:
    """Install the compressed manual page."""
    man_dir = package_dir / "usr" / "share" / "man" / "man1"
    man_dir.mkdir(parents=True, exist_ok=True)

    with (
        (linux_assets_dir / "tapmap.1").open("rb") as src,
        gzip.open(man_dir / "tapmap.1.gz", "wb") as dst,
    ):
        shutil.copyfileobj(src, dst)


def compute_linux_dependencies(
    package_dir: Path,
    executable: Path,
) -> str:
    """Compute shared-library dependencies using dpkg-shlibdeps."""
    debian_dir = package_dir / "debian"
    debian_dir.mkdir(exist_ok=True)

    (debian_dir / "control").write_text(
        """Source: tapmap

Package: tapmap
Architecture: amd64
""",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "dpkg-shlibdeps",
            "-O",
            str(executable.relative_to(package_dir)),
        ],
        cwd=package_dir,
        capture_output=True,
        text=True,
        check=True,
    )

    output = result.stdout.strip()

    prefix = "shlibs:Depends="
    if output.startswith(prefix):
        shutil.rmtree(debian_dir)
        return output.removeprefix(prefix)

    raise RuntimeError(f"Unexpected dpkg-shlibdeps output:\n{output}")


# Packaging
def package_windows() -> None:
    """Create Windows release artifacts.

    Future:
    - Run Inno Setup.
    - Submit installer to SignPath.
    - Download signed installer.
    """
    pass


def package_linux() -> None:
    """Create Linux release artifacts.

    - Build DEB.

    Future:
    - Build AppImage.
    - Build RPM.
    """
    if not sys.platform.startswith("linux"):
        return

    project = project_metadata()
    print(f"Packaging {project['name']} {project['version']}")

    rm_tree(PACKAGE_DIR)
    PACKAGE_DIR.mkdir(exist_ok=True)
    (PACKAGE_DIR / "DEBIAN").mkdir()
    (PACKAGE_DIR / "usr" / "bin").mkdir(parents=True)
    (PACKAGE_DIR / "usr" / "lib" / "tapmap").mkdir(parents=True)
    (PACKAGE_DIR / "usr" / "share" / "applications").mkdir(parents=True)
    (PACKAGE_DIR / "usr" / "share" / "metainfo").mkdir(parents=True)
    (PACKAGE_DIR / "usr" / "share" / "doc" / project["name"]).mkdir(parents=True)
    (PACKAGE_DIR / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps").mkdir(parents=True)
    ICONS_DIR = PROJECT_ROOT / "src" / "tapmap" / "assets" / "icons"
    LINUX_ASSETS_DIR = PROJECT_ROOT / "src" / "tapmap" / "assets" / "linux"
    DOC_DIR = PACKAGE_DIR / "usr" / "share" / "doc" / project["name"]

    copy_linux_icons(PACKAGE_DIR, ICONS_DIR)

    # Install the application under /usr/lib and expose it via /usr/bin.
    # This follows the Debian filesystem hierarchy.
    shutil.copy2(
        DIST_DIR / DIST_NAME,
        PACKAGE_DIR / "usr" / "lib" / "tapmap" / DIST_NAME,
    )

    (PACKAGE_DIR / "usr" / "bin" / "tapmap").symlink_to("../lib/tapmap/tapmap")

    # Install AppStream metadata used by software centers.
    shutil.copy2(
        LINUX_ASSETS_DIR / "no.tip.tapmap.metainfo.xml",
        PACKAGE_DIR / "usr" / "share" / "metainfo" / "no.tip.tapmap.metainfo.xml",
    )

    # Install Debian package documentation required by policy.
    write_debian_changelog(DOC_DIR, project)

    install_manual_page(
        PACKAGE_DIR,
        LINUX_ASSETS_DIR,
    )

    shutil.copy2(
        PROJECT_ROOT / "LICENSE",
        DOC_DIR / "copyright",
    )

    executable = PACKAGE_DIR / "usr" / "lib" / "tapmap" / DIST_NAME

    depends = compute_linux_dependencies(
        PACKAGE_DIR,
        executable,
    )

    executable.chmod(0o755)
    write_debian_control(
        PACKAGE_DIR,
        project,
        depends,
    )
    write_desktop_file(PACKAGE_DIR, project)

    # Normalize permissions for all packaged files.
    # Restore execute permission on the application afterwards.
    for path in PACKAGE_DIR.rglob("*"):
        if path.is_dir():
            path.chmod(0o755)
        else:
            path.chmod(0o644)

    executable.chmod(0o755)

    deb_file = DIST_DIR / f"{project['name']}-{project['version']}-amd64.deb"

    # Build the Debian package.
    # Record all files as owned by root inside the package archive.
    run(
        [
            "dpkg-deb",
            "--build",
            "--root-owner-group",
            str(PACKAGE_DIR),
            str(deb_file),
        ]
    )

    if not deb_file.exists():
        raise FileNotFoundError(f"DEB was not created: {deb_file}")

    rm_tree(PACKAGE_DIR)

    print(f"[OK] Package Linux release ({deb_file.name})")


def package_macos() -> None:
    """Create macOS release artifacts."""
    if sys.platform != "darwin":
        return

    rm_tree(DMG_DIR)
    rm_tree(PACKAGE_DIR)

    DMG_DIR.mkdir(exist_ok=True)
    PACKAGE_DIR.mkdir(exist_ok=True)

    shutil.copytree(
        DIST_DIR / MACOS_APP_NAME,
        PACKAGE_DIR / MACOS_APP_NAME,
    )

    dmg_file = DMG_DIR / MACOS_DMG_NAME

    run(
        [
            "create-dmg",
            # Enable when GitHub Actions provides create-dmg >= 1.3.0.
            # "--overwrite",
            "--volname",
            "TapMap",
            "--window-size",
            "600",
            "400",
            "--icon-size",
            "128",
            "--icon",
            MACOS_APP_NAME,
            "160",
            "180",
            "--app-drop-link",
            "440",
            "180",
            str(dmg_file),
            str(PACKAGE_DIR),
        ]
    )

    if not dmg_file.exists():
        raise FileNotFoundError(f"DMG was not created: {dmg_file}")

    rm_tree(PACKAGE_DIR)
    print(f"[OK] Package macOS release ({dmg_file.name})")


def package_release() -> None:
    """Create platform-specific release artifacts."""
    if sys.platform == "darwin":
        package_macos()
    elif sys.platform.startswith("linux"):
        package_linux()
    elif os.name == "nt":
        package_windows()
    else:
        raise RuntimeError(f"Unsupported platform: {sys.platform}")


# Signing
def sign_windows() -> None:
    """Code sign Windows release artifacts."""
    pass


def sign_linux() -> None:
    """Code sign Linux release artifacts."""
    pass


def sign_macos() -> None:
    """Code sign macOS release artifacts."""
    pass


def sign_release() -> None:
    """Code sign release artifacts."""
    if sys.platform == "darwin":
        sign_macos()
    elif sys.platform.startswith("linux"):
        sign_linux()
    elif os.name == "nt":
        sign_windows()
    else:
        raise RuntimeError(f"Unsupported platform: {sys.platform}")


def verify_signature() -> None:
    """Verify digital signature of release artifacts."""
    pass


# Notarization
def notarize_release() -> None:
    """Submit release for Apple notarization."""
    pass


def staple_notarization() -> None:
    """Staple Apple notarization ticket."""
    pass


def verify_gatekeeper() -> None:
    """Verify Gatekeeper acceptance."""
    pass


# Publishing
def publish_release() -> None:
    """Publish release artifacts."""
    pass


def main() -> None:
    """Build TapMap release artifacts."""
    print("=" * 62)
    print("TapMap Release Build")
    print("=" * 62)

    if not SPEC_FILE.exists():
        raise FileNotFoundError(f"Spec file not found: {SPEC_FILE}")

    clean()
    build_pyinstaller()
    verify_build()
    package_release()
    # TODO:
    # sign_release()
    # verify_signature()
    # notarize_release()
    # staple_notarization()
    # verify_gatekeeper()
    # publish_release()

    print()
    print("=" * 62)
    print("Build completed successfully.")

    if sys.platform == "darwin":
        print(f"Application : {(DIST_DIR / MACOS_APP_NAME).resolve()}")
        print(f"Installer   : {(DMG_DIR / MACOS_DMG_NAME).resolve()}")

    print("=" * 62)


if __name__ == "__main__":
    main()
