from pathlib import Path

import mkdocs_gen_files

ROOT = Path(__file__).resolve().parents[1]

EXCLUDE_DIRS = {
    ".venv",
    ".private",
    ".github",
    "docs",
    "site",
    "tools",
}

nav = mkdocs_gen_files.Nav()


for path in sorted(ROOT.rglob("*.py")):
    if any(part in EXCLUDE_DIRS for part in path.parts):
        continue

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

    doc_path = Path("reference", doc_rel_path)
    nav[nav_parts] = doc_rel_path.as_posix()

    with mkdocs_gen_files.open(doc_path, "w") as f:
        f.write(f"# `{module_name}`\n\n")
        f.write(f"::: {module_name}\n")

with mkdocs_gen_files.open("reference/SUMMARY.md", "w") as nav_file:
    nav_file.writelines(nav.build_literate_nav())
