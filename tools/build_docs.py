from pathlib import Path

import mkdocs_gen_files

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
REFERENCE_ROOT = Path("reference")
README_PATH = ROOT / "README.md"
INDEX_PATH = Path("index.md")
PRIVACY_PATH = ROOT / "PRIVACY.md"
PRIVACY_DOC_PATH = Path("privacy.md")
CONTRIBUTING_PATH = ROOT / "CONTRIBUTING.md"
CONTRIBUTING_DOC_PATH = Path("contributing.md")
ARCHITECTURE_PATH = ROOT / "ARCHITECTURE.md"
ARCHITECTURE_DOC_PATH = Path("architecture.md")
SECURITY_PATH = ROOT / "SECURITY.md"
SECURITY_DOC_PATH = Path("security.md")

EXCLUDE_DIRS = {
    "__pycache__",
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
    content = content.replace("(PRIVACY.md)", "(privacy.md)")

    with mkdocs_gen_files.open(INDEX_PATH, "w") as file:
        file.write(content)


def write_privacy_page() -> None:
    """Write docs privacy page from PRIVACY.md."""
    content = PRIVACY_PATH.read_text(encoding="utf-8")
    content = content.replace("(docs/images/", "(images/")
    content = content.replace('src="docs/images/', 'src="images/')

    with mkdocs_gen_files.open(PRIVACY_DOC_PATH, "w") as file:
        file.write(content)


def write_reference_page(doc_path: Path, module_name: str) -> None:
    """Write one generated API reference page."""
    with mkdocs_gen_files.open(doc_path, "w") as file:
        file.write(f"# `{module_name}`\n\n")
        file.write(f"::: {module_name}\n")
        file.write("    options:\n")
        file.write("      members: true\n")


def write_contributing_page() -> None:
    """Write docs contributing page from CONTRIBUTING.md."""
    content = CONTRIBUTING_PATH.read_text(encoding="utf-8")
    content = content.replace("(ARCHITECTURE.md)", "(architecture.md)")
    content = content.replace("(SECURITY.md)", "(security.md)")

    with mkdocs_gen_files.open(CONTRIBUTING_DOC_PATH, "w") as file:
        file.write(content)


def write_architecture_page() -> None:
    """Write docs architecture page from ARCHITECTURE.md."""
    content = ARCHITECTURE_PATH.read_text(encoding="utf-8")
    content = content.replace("(README.md)", "(index.md)")
    content = content.replace("(CONTRIBUTING.md)", "(contributing.md)")
    content = content.replace("(SECURITY.md)", "(security.md)")
    content = content.replace("(docs/", "(")

    with mkdocs_gen_files.open(ARCHITECTURE_DOC_PATH, "w") as file:
        file.write(content)


def write_security_page() -> None:
    """Write docs security page from SECURITY.md."""
    content = SECURITY_PATH.read_text(encoding="utf-8")

    with mkdocs_gen_files.open(SECURITY_DOC_PATH, "w") as file:
        file.write(content)


def main() -> None:
    """Build generated docs pages."""
    nav = mkdocs_gen_files.Nav()

    write_home_page()
    write_privacy_page()
    write_contributing_page()
    write_architecture_page()
    write_security_page()

    for path in iter_python_files(SRC_ROOT):
        module_path = path.relative_to(SRC_ROOT).with_suffix("")
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
