"""Linux build pipeline."""

import sys

from build_common import (
    build_pyinstaller,
    clean,
    run,
    verify_build,
)


def setup() -> None:
    """Prepare the build environment."""
    clean()

def run_tests() -> None:
    """Run automated tests."""
    run([sys.executable, "-m", "pytest"])

def build_application() -> None:
    """Build the application."""
    build_pyinstaller()


def verify_application() -> None:
    """Verify the application build."""
    verify_build()


def package() -> None:
    """Create the release package."""
    raise NotImplementedError


def sign() -> None:
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


def pipeline() -> None:
    """Build the release package."""
    setup()
    run_tests()
    build_application()
    verify_application()
    package()
    sign()
    notarize()
    staple()
    verify_package()
