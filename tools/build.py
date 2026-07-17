#!/usr/bin/env python3
"""Build TapMap for the current operating system."""

import sys

import build_linux
import build_macos
import build_windows


def main() -> None:
    """Run the build pipeline for the current operating system."""
    if sys.platform.startswith("linux"):
        build_linux.pipeline()
    elif sys.platform == "win32":
        build_windows.pipeline()
    elif sys.platform == "darwin":
        build_macos.pipeline()
    else:
        raise RuntimeError(f"Unsupported platform: {sys.platform}")


if __name__ == "__main__":
    main()
