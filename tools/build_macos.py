"""Build the macOS release package for TapMap.

Pipeline
--------
1. Clean previous build artifacts.
2. Run automated tests.
3. Build and sign the application with PyInstaller.
4. Verify the application signature.
5. Package the application as a DMG.
6. Sign, notarize and staple the DMG during packaging.
7. Verify the packaged release.

Implementation
--------------
- Entry point: python tools/build.py [--sign]
- Application signing is performed by PyInstaller using the signing
  identity provided to tapmap.spec at build time.
- DMG signing, notarization and stapling are performed by create-dmg
  during packaging.
"""

from pathlib import Path

from build_common import (
    BUILD_DIR,
    DIST_DIR,
    PACKAGE_DIR,
    build_application,
    get_signing_identity,
    require_tool,
    rm_tree,
    run,
    run_tests,
)

APP_NAME = "TapMap.app"
DMG_NAME = "TapMap.dmg"
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


def sign_application() -> None:
    """Sign the application bundle."""
    app = expected_output_file()

    run(
        [
            "codesign",
            "--force",
            "--options",
            "runtime",
            "--timestamp",
            "--sign",
            get_signing_identity(),
            str(app),
        ],
        capture_output=True,
    )

    print(f"[OK] Signed application ({app.name})")


def verify_application(sign: bool = False) -> None:
    """Verify the application bundle."""
    app = expected_output_file()

    if not app.exists():
        raise FileNotFoundError(f"Expected output not found: {app}")

    if sign:
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


def package() -> None:
    """Create macOS release artifacts."""
    rm_tree(PACKAGE_DIR)
    PACKAGE_DIR.mkdir(exist_ok=True)

    run(
        [
            "ditto",
            str(DIST_DIR / APP_NAME),
            str(PACKAGE_DIR / APP_NAME),
        ]
    )

    dmg_file = DIST_DIR / DMG_NAME

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
            "tapmap-notary",
            str(dmg_file),
            str(PACKAGE_DIR),
        ],
        capture_output=True,
    )

    if not dmg_file.exists():
        raise FileNotFoundError(f"DMG was not created: {dmg_file}")

    rm_tree(PACKAGE_DIR)

    print(f"[OK] Package macOS release ({dmg_file.name})")


def verify_package(sign: bool = False) -> None:
    """Verify the release package."""
    package = DIST_DIR / "TapMap.dmg"

    if not package.exists():
        raise FileNotFoundError(f"Expected package not found: {package}")

    if sign:
        run(
            [
                "xcrun",
                "stapler",
                "validate",
                str(package),
            ]
        )

    print(f"[OK] Verified package ({package.name})")


def pipeline(sign: bool = False) -> None:
    """Build the release package."""
    setup()
    run_tests()
    build_application()
    verify_application(sign=sign)
    package()
    verify_package(sign=sign)
