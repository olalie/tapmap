"""Regenerate requirements-docs.txt from TapMap's direct MkDocs dependencies.

Package versions are resolved exclusively from this interpreter's own
environment (importlib.metadata), never from PyPI and never via `pip
freeze` against whatever "pip" happens to be on PATH. Review the
resulting change with `git diff requirements-docs.txt` before
committing.

DIRECT_PACKAGES below is hand-maintained against mkdocs.yml's
theme/plugins/markdown_extensions and any packages imported directly
in tools/build_docs.py - update it whenever those change.

Run from the project root:
    python tools/mkdocsreq.py
"""

from __future__ import annotations

import subprocess
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
OUTPUT = ROOT / "requirements-docs.txt"

DIRECT_PACKAGES = {
    "mkdocs",  # core tool
    "mkdocs-material",  # theme.name: material
    "mkdocs-gen-files",  # plugins: gen-files; imported in build_docs.py
    "mkdocs-literate-nav",  # plugins: literate-nav; used in build_docs.py
    "mkdocstrings",  # plugins: mkdocstrings
    "mkdocstrings-python",  # handlers: python
    "pymdown-extensions",  # markdown_extensions: pymdownx.*
}


def check_venv_interpreter() -> None:
    """Verify this process is running the project's .venv python.

    Raises:
        SystemExit: if running under a different interpreter, since
            package versions would then be resolved from the wrong
            environment.
    """
    if Path(sys.prefix).resolve() != VENV.resolve():
        raise SystemExit(
            f"mkdocsreq.py must run under the project's .venv interpreter, not {sys.prefix}. "
            f"Run: {VENV / 'Scripts' / 'python.exe'} {Path(__file__).resolve()}"
        )


def resolve_versions(names: set[str]) -> dict[str, str]:
    """Map package names to installed versions.

    Raises:
        SystemExit: if a listed package is not installed in this
            interpreter's environment.
    """
    result: dict[str, str] = {}
    missing: list[str] = []

    for name in sorted(names):
        try:
            result[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            missing.append(name)

    if missing:
        raise SystemExit(
            f"Not installed in {sys.prefix}: {', '.join(missing)}. "
            "Install them in .venv, or if they are no longer direct "
            "dependencies, remove them from DIRECT_PACKAGES in tools/mkdocsreq.py."
        )

    return result


def show_diff() -> None:
    """Print the working-tree diff for requirements-docs.txt against HEAD."""
    print()
    print("Differences:", flush=True)
    subprocess.run(
        ["git", "--no-pager", "diff", "--", OUTPUT.name],
        cwd=ROOT,
        check=False,
    )


def main() -> None:
    """Regenerate requirements-docs.txt from DIRECT_PACKAGES."""
    check_venv_interpreter()

    versions = resolve_versions(DIRECT_PACKAGES)
    lines = [
        f"{name}=={version}"
        for name, version in sorted(versions.items(), key=lambda item: item[0].lower())
    ]
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    show_diff()


if __name__ == "__main__":
    main()
