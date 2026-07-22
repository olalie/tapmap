"""Build the Windows release package for TapMap.

Pipeline
--------
1. Clean previous build artifacts.
2. Verify required build tools.
3. Run automated tests.
4. Build the application with PyInstaller.
5. Verify the application build.
6. Package the application as an Inno Setup installer.
7. Verify the packaged release.

Implementation
--------------
- Entry point: python tools/build.py
- Application is built as a PyInstaller onedir distribution.
- The installer is created with Inno Setup (TapMap.iss).
- Official release signing is performed by the GitHub Actions
  pipeline using SignPath.
- Local builds are not code signed.
"""

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
    print("[OK] Clean build directories")


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

    print(f"[OK] Verify build ({app.name})")


def setup_name(version: str) -> str:
    """Return the Windows installer filename."""
    return f"TapMap-{version}-windows-x64-Setup"


def package() -> None:
    """Create the release package."""
    project = project_metadata()
    version = project["version"]
    output = setup_name(version)
    exe = expected_output_file()
    icon = PROJECT_ROOT / "src" / "tapmap" / "assets" / "tapmap.ico"

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
    package = DIST_DIR / f"{setup_name(project['version'])}.exe"

    if not package.exists():
        raise FileNotFoundError(f"Expected package not found: {package}")

    print(f"[OK] Verified package ({package.name})")


def pipeline() -> None:
    """Build the Windows application and installer."""
    setup()
    run_tests()
    build_application()
    verify_application()
    package()
    verify_package()
