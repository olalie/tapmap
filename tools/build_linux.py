"""Build the Linux release package for TapMap.

Pipeline
--------
1. Clean previous build artifacts.
2. Run automated tests.
3. Build the application with PyInstaller.
4. Verify the application build.
5. Package the application as a Debian package.
6. Verify the packaged release.

Implementation
--------------
- Entry point: python tools/build.py [--sign]
- Application is built as a PyInstaller onedir distribution.
- Packaging follows the Debian filesystem hierarchy.
- Shared-library dependencies are determined automatically using
  dpkg-shlibdeps.
- The package includes desktop integration, AppStream metadata,
  application icons and a compressed manual page.
- Future packaging targets include AppImage and RPM.
"""

import gzip
import shutil
import subprocess
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path

from build_common import (
    BUILD_DIR,
    DIST_DIR,
    PACKAGE_DIR,
    PROJECT_ROOT,
    build_application,
    project_metadata,
    rm_tree,
    run,
    run_tests,
)

EXECUTABLE_NAME = "tapmap"


def clean() -> None:
    """Remove previous build artifacts."""
    rm_tree(BUILD_DIR)
    rm_tree(DIST_DIR)
    rm_tree(PACKAGE_DIR)
    print("[OK] Clean build directories")


def setup() -> None:
    """Prepare the build environment."""
    clean()


def expected_output_file() -> Path:
    """Return the expected PyInstaller output."""
    return DIST_DIR / EXECUTABLE_NAME


def verify_application() -> None:
    """Verify the application build."""
    app = expected_output_file()

    if not app.exists():
        raise FileNotFoundError(f"Expected output not found: {app}")

    print(f"[OK] Verify build ({app.name})")


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


def deb_name(version: str) -> str:
    """Return the Linux package filename."""
    return f"TapMap-{version}-linux-amd64.deb"


def package() -> None:
    """Create the release package.

    - Build DEB.

    Future:
    - Build AppImage.
    - Build RPM.
    """
    project = project_metadata()
    package_name = deb_name(project["version"])
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
    shutil.copytree(
        DIST_DIR / EXECUTABLE_NAME,
        PACKAGE_DIR / "usr" / "lib" / "tapmap",
        dirs_exist_ok=True,
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

    executable = PACKAGE_DIR / "usr" / "lib" / "tapmap" / EXECUTABLE_NAME

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

    deb_file = DIST_DIR / package_name

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


def verify_package(sign: bool = False) -> None:
    """Verify the release package."""
    project = project_metadata()
    package = DIST_DIR / deb_name(project["version"])

    if not package.exists():
        raise FileNotFoundError(f"Expected package not found: {package}")

    print(f"[OK] Verified package ({package.name})")


def pipeline(sign: bool = False) -> None:
    """Build the release package."""
    _ = sign  # Reserved for future package signing.

    setup()
    run_tests()
    build_application()
    verify_application()
    package()
    verify_package()
