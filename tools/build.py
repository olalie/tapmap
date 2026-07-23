#!/usr/bin/env python3
"""Build TapMap for the current operating system."""

import argparse
import sys

import build_linux
import build_macos
import build_windows


def main() -> None:
    """Run the build pipeline for the current operating system."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--package",
        action="store_true",
        help="Create a release package.",
    )
    args = parser.parse_args()

    if sys.platform == "win32":
        build_windows.pipeline(package=args.package)
    elif sys.platform == "darwin":
        build_macos.pipeline(sign=args.package)
    elif sys.platform.startswith("linux"):
        build_linux.pipeline(package=args.package)
    else:
        raise RuntimeError(f"Unsupported platform: {sys.platform}")


if __name__ == "__main__":
    main()
