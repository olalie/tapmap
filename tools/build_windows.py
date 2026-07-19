"""Windows build pipeline."""

from pathlib import Path

from build_common import (
    BUILD_DIR,
    DIST_DIR,
    PACKAGE_DIR,
    PROJECT_ROOT,
    build_application,
    project_metadata,
    require_tool,
    rm_tree,
    run,
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
    require_tool("iscc")


def expected_output_file() -> Path:
    """Return the expected PyInstaller output."""
    return DIST_DIR / "tapmap" / "tapmap.exe"

def verify_application() -> None:
    """Verify the application build."""
    app = expected_output_file()

    if not app.exists():
        raise FileNotFoundError(f"Expected output not found: {app}")

    print(f"✓ Verify build ({app.name})")


def package() -> None:
    """Create the release package."""
    project = project_metadata()
    version = project["version"]
    exe = expected_output_file()
    icon = PROJECT_ROOT / "src" / "tapmap" / "assets" / "tapmap.ico"
    output = f"TapMap-{version}-Setup"

    run(
        [
            "iscc",
            f"/DMyAppVersion={version}",
            f"/DMyAppExePath={exe}",
            f"/DMySetupIcon={icon}",
            f"/DMyOutputDir={DIST_DIR}",
            f"/DMyOutputBaseFilename={output}",
            str(PROJECT_ROOT / "tools" / "windows" / "TapMap.iss"),
        ],
        capture_output=True,
    )


def verify_package(sign: bool = False) -> None:
    """Verify the release package."""
    project = project_metadata()
    package = DIST_DIR / f"{project['name']}-{project['version']}-Setup.exe"

    if not package.exists():
        raise FileNotFoundError(f"Expected package not found: {package}")

    print(f"✓ Verified package ({package.name.lower()})")


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
