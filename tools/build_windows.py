"""Windows build pipeline."""

import sys
from pathlib import Path

from build_common import (
    BUILD_DIR,
    DIST_DIR,
    PACKAGE_DIR,
    build_application,
    rm_tree,
    run_tests,
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


def expected_output_file() -> Path:
    """Return the expected PyInstaller output."""
    return DIST_DIR / "tapmap.exe"


def verify_application() -> None:
    """Verify the application build."""
    app = expected_output_file()

    if not app.exists():
        raise FileNotFoundError(f"Expected output not found: {app}")

    print(f"✓ Verify build ({app.name})")


def package() -> None:
    """Create the release package."""
    raise NotImplementedError


def verify_package() -> None:
    """Verify the final release package."""
    raise NotImplementedError


def pipeline(sign: bool = False) -> None:
    """Build the release package."""
    setup()
    run_tests()
    build_application()
    # TODO: Add code signing once a signing solution is available.
    verify_application()
    package()
    # TODO: Add code signing once a signing solution is available.
    verify_package()
