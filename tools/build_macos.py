"""Build the macOS release package for TapMap.

Pipeline
--------
1. Clean previous build artifacts.
2. Run automated tests.
3. Build the application with PyInstaller.
4. Verify the application's signature.
5. (Optional) Require a real Developer ID identity, then package the
   application as a DMG.
6. (Optional) Sign, notarize and staple the DMG during packaging.
7. (Optional) Verify the packaged release.

Implementation
--------------
- Entry point: python tools/build.py [--package]
- Application signing is performed by PyInstaller using the signing
  identity provided to tapmap.spec at build time, falling back to ad-hoc
  signing when no Developer ID identity is available, so a local build
  works without TIP's certificate.
- Autostart uses SMAppService.mainApp, registered by TapMap itself at
  runtime (see tapmap.autostart.macos_service_management); nothing is
  bundled into the app at build time for it.
- DMG signing, notarization and stapling are performed by create-dmg
  during packaging; create-dmg signs and notarizes the DMG only, not
  TapMap.app, which must already be validly signed before it runs. Unlike
  the local build, packaging requires a real Developer ID identity and
  fails immediately, before any build work runs, if one isn't available.
"""

import platform
from pathlib import Path

from build_common import (
    BUILD_DIR,
    DIST_DIR,
    PACKAGE_DIR,
    build_application,
    get_signing_identity,
    project_metadata,
    require_tool,
    rm_tree,
    run,
    run_tests,
)

APP_NAME = "TapMap.app"
SIGNING_IDENTITY: str | None = None
NOTARY_PROFILE = "tapmap-notary"


def clean() -> None:
    """Remove previous build artifacts."""
    rm_tree(BUILD_DIR)
    rm_tree(DIST_DIR)
    rm_tree(PACKAGE_DIR)
    print("[OK] Clean build directories")


def setup() -> None:
    """Prepare the build environment."""
    clean()
    require_tool("create-dmg")


def expected_output_file() -> Path:
    """Return the expected PyInstaller output."""
    return DIST_DIR / APP_NAME


def require_signing_identity() -> None:
    """Raise an error if no Developer ID Application identity is available.

    Release packaging must not silently fall back to ad-hoc signing.
    """
    if get_signing_identity() is None:
        raise RuntimeError(
            "No Developer ID Application identity found. Import TIP's Developer ID "
            "certificate before running with --package; ordinary local builds "
            "(without --package) don't need it."
        )


def verify_application() -> None:
    """Verify the application bundle's code signature."""
    app = expected_output_file()

    if not app.exists():
        raise FileNotFoundError(f"Expected output not found: {app}")

    run(
        [
            "codesign",
            "--verify",
            "--deep",
            "--strict",
            # "--verbose=2",
            str(app),
        ]
    )

    print(f"[OK] Verified application ({app.name})")


def current_arch() -> str:
    """Return normalized architecture name."""
    arch = platform.machine().lower()

    if arch == "amd64":
        return "x86_64"
    if arch == "aarch64":
        return "arm64"

    return arch


def dmg_name(version: str) -> str:
    """Return the macOS package filename."""
    return f"TapMap-{version}-macos-{current_arch()}.dmg"


def package_release() -> None:
    """Create macOS release artifacts."""
    rm_tree(PACKAGE_DIR)
    PACKAGE_DIR.mkdir(exist_ok=True)
    project = project_metadata()
    version = project["version"]
    package_name = dmg_name(version)

    run(
        [
            "ditto",
            str(DIST_DIR / APP_NAME),
            str(PACKAGE_DIR / APP_NAME),
        ]
    )

    dmg_file = DIST_DIR / package_name

    _ = run(
        [
            "create-dmg",
            # Enable when GitHub Actions provides create-dmg >= 1.3.0.
            # "--overwrite",
            "--no-internet-enable",
            "--hdiutil-quiet",
            "--volname",
            "TapMap",
            "--window-size",
            "600",
            "400",
            "--icon-size",
            "128",
            "--icon",
            APP_NAME,
            "160",
            "180",
            "--hide-extension",
            APP_NAME,
            "--app-drop-link",
            "440",
            "180",
            "--codesign",
            get_signing_identity(),
            "--notarize",
            NOTARY_PROFILE,
            str(dmg_file),
            str(PACKAGE_DIR),
        ],
        capture_output=True,
    )

    if not dmg_file.exists():
        raise FileNotFoundError(f"DMG was not created: {dmg_file}")

    rm_tree(PACKAGE_DIR)

    print(f"[OK] Package macOS release ({dmg_file.name})")


def verify_package() -> None:
    """Verify the release package."""
    project = project_metadata()
    package = DIST_DIR / dmg_name(project["version"])

    if not package.exists():
        raise FileNotFoundError(f"Expected package not found: {package}")

    run(
        [
            "xcrun",
            "stapler",
            "validate",
            str(package),
        ]
    )

    print(f"[OK] Verified package ({package.name})")


def pipeline(package: bool = False) -> None:
    """Build the macOS application and optionally package it."""
    if package:
        require_signing_identity()

    setup()
    run_tests()
    build_application()
    verify_application()

    if package:
        package_release()
        verify_package()
