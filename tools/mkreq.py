"""Regenerate requirements.txt from imports found under src/.

Package names and versions are resolved exclusively from this
interpreter's own environment (importlib.metadata), never from PyPI
and never via a filesystem walk that could reach a different
environment's site-packages. Review the resulting change with
`git diff requirements.txt` before committing.

Linux desktop-only dependencies are maintained separately in
requirements-linux-desktop.txt and are outside this tool's scope.

Run from the project root:
    python tools/mkreq.py
"""

from __future__ import annotations

import ast
import subprocess
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
VENV = ROOT / ".venv"
OUTPUT = ROOT / "requirements.txt"

# .NET namespaces exposed via pythonnet's CLR import hook (see
# windows_signature_info.py). Not PyPI packages; "clr" itself resolves
# normally, to the pythonnet distribution.
DOTNET_NAMESPACES = {"Microsoft", "System"}


def check_venv_interpreter() -> None:
    """Verify this process is running the project's .venv python.

    Raises:
        SystemExit: if running under a different interpreter, since
            package versions would then be resolved from the wrong
            environment.
    """
    if Path(sys.prefix).resolve() != VENV.resolve():
        raise SystemExit(
            f"mkreq.py must run under the project's .venv interpreter, not {sys.prefix}. "
            f"Run: {VENV / 'Scripts' / 'python.exe'} {Path(__file__).resolve()}"
        )


def find_imports(src: Path) -> set[str]:
    """Return top-level import names used anywhere under src."""
    names: set[str] = set()

    for path in src.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.add(node.module.split(".")[0])

    return names


def self_package_names(src: Path) -> set[str]:
    """Return top-level package/module names defined under src."""
    names = {path.stem for path in src.glob("*.py")}
    names |= {
        path.name for path in src.iterdir() if path.is_dir() and (path / "__init__.py").is_file()
    }
    return names


def resolve_distributions(import_names: set[str]) -> dict[str, str]:
    """Map import names to installed distribution name/version pairs.

    Raises:
        SystemExit: if an import cannot be mapped to a distribution
            installed in this interpreter's environment.
    """
    packages_by_module = metadata.packages_distributions()
    result: dict[str, str] = {}
    unresolved: list[str] = []

    for name in sorted(import_names):
        if name in sys.stdlib_module_names or name in DOTNET_NAMESPACES:
            continue

        distributions = packages_by_module.get(name)
        if not distributions:
            unresolved.append(name)
            continue

        dist_name = distributions[0]
        result[dist_name] = metadata.version(dist_name)

    if unresolved:
        raise SystemExit(
            f"No package installed in {sys.prefix} provides: {', '.join(unresolved)}. "
            "Install the package in .venv, or if it is not a real PyPI "
            "dependency, add it to DOTNET_NAMESPACES in tools/mkreq.py."
        )

    return result


def format_requirement(name: str, version: str) -> str:
    """Format one requirements.txt line, with platform markers where needed."""
    if name == "pythonnet":
        return f'{name}=={version}; sys_platform == "win32"'
    return f"{name}=={version}"


def show_diff() -> None:
    """Print the working-tree diff for requirements.txt against HEAD."""
    print()
    print("Differences:", flush=True)
    subprocess.run(
        ["git", "--no-pager", "diff", "--", OUTPUT.name],
        cwd=ROOT,
        check=False,
    )


def main() -> None:
    """Regenerate requirements.txt from imports found under src/."""
    check_venv_interpreter()

    imports = find_imports(SRC) - self_package_names(SRC)
    distributions = resolve_distributions(imports)

    lines = [
        format_requirement(name, version)
        for name, version in sorted(distributions.items(), key=lambda item: item[0].lower())
    ]
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    show_diff()


if __name__ == "__main__":
    main()
