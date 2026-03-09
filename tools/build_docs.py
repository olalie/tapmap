from pathlib import Path

import mkdocs_gen_files

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_ROOT = Path("reference")
README_PATH = ROOT / "README.md"
INDEX_PATH = Path("index.md")

EXCLUDE_DIRS = {
    ".venv",
    ".private",
    ".github",
    "docs",
    "site",
    "tools",
}


def iter_python_files(root: Path) -> list[Path]:
    """Return Python files to document."""
    files: list[Path] = []

    for path in sorted(root.rglob("*.py")):
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        files.append(path)

    return files


def write_home_page() -> None:
    """Write docs home page from README.md."""
    content = README_PATH.read_text(encoding="utf-8")
    content = content.replace("(docs/images/", "(images/")
    content = content.replace('src="docs/images/', 'src="images/')

    with mkdocs_gen_files.open(INDEX_PATH, "w") as file:
        file.write(content)


def write_reference_page(doc_path: Path, module_name: str) -> None:
    """Write one generated API reference page."""
    with mkdocs_gen_files.open(doc_path, "w") as file:
        file.write(f"# `{module_name}`\n\n")
        file.write(f"::: {module_name}\n")
        file.write("    options:\n")
        file.write("      members: true\n")


def main() -> None:
    """Build generated docs pages."""
    nav = mkdocs_gen_files.Nav()

    write_home_page()

    for path in iter_python_files(ROOT):
        module_path = path.relative_to(ROOT).with_suffix("")
        parts = module_path.parts

        if parts[-1] == "__init__":
            module_name = ".".join(parts[:-1])
            doc_rel_path = Path(*parts[:-1], "index.md")
            nav_parts = parts[:-1]
        else:
            module_name = ".".join(parts)
            doc_rel_path = Path(*parts).with_suffix(".md")
            nav_parts = parts

        doc_path = REFERENCE_ROOT / doc_rel_path
        nav[nav_parts] = doc_rel_path.as_posix()
        write_reference_page(doc_path, module_name)

    with mkdocs_gen_files.open(REFERENCE_ROOT / "SUMMARY.md", "w") as nav_file:
        nav_file.writelines(nav.build_literate_nav())


main()
