"""Windows build pipeline."""

import sys
from pathlib import Path

from build_common import (
    BUILD_DIR,
    DIST_DIR,
    PACKAGE_DIR,
    build_pyinstaller,
    rm_tree,
    run,
)


def clean() -> None:
    """Remove previous build artifacts."""
    rm_tree(BUILD_DIR)
    rm_tree(DIST_DIR)
    rm_tree(PACKAGE_DIR)
    print("✓ Clean build directories")


def setup() -> None:
    """Prepare the build environment."""
    clean()


def run_tests() -> None:
    """Run automated tests."""
    run([sys.executable, "-m", "pytest"])


def build_application() -> None:
    """Build the application."""
    build_pyinstaller()


def expected_output_file() -> Path:
    """Return the expected PyInstaller output."""
    return DIST_DIR / "tapmap.exe"


def verify_application() -> None:
    """Verify the application build."""
    app = expected_output_file()

    if not app.exists():
        raise FileNotFoundError(f"Expected output not found: {app}")

    print(f"✓ Verify build ({app.name})")


def sign_application() -> None:
    """Sign the application bundle."""
    raise NotImplementedError


def package() -> None:
    """Create the release package."""
    raise NotImplementedError


def sign_package() -> None:
    """Sign the release package."""
    raise NotImplementedError


def notarize() -> None:
    """Submit the release package for notarization."""
    raise NotImplementedError


def staple() -> None:
    """Attach the notarization ticket."""
    raise NotImplementedError


def verify_package() -> None:
    """Verify the final release package."""
    raise NotImplementedError


def pipeline(sign: bool = False) -> None:
    """Build the release package."""
    setup()
    run_tests()
    build_application()

    if sign:
        sign_application()

    verify_application()
    package()

    if sign:
        sign_package()
        notarize()
        staple()

    verify_package()
