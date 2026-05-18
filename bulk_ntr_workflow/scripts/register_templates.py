#!/usr/bin/env python3
"""Stage 5: register bulk-NTR templates with ODK and regenerate the Makefile.

Discovers `src/templates/<name>*.template.tsv` files produced by Stage 4
(`merge_definitions.py`) and registers any that are not yet listed under
`components.products:` in `src/ontology/uberon-odk.yaml`. Then runs
`sh run.sh make update_repo` from `src/ontology/` so the Makefile picks
up the new components.

Idempotent: re-running after a successful registration is a no-op for
already-registered templates.

Usage:
    uv run scripts/register_templates.py --name hra-muscular
    uv run scripts/register_templates.py --name hra-muscular --skip-update-repo
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = REPO_ROOT / "src" / "templates"
ODK_YAML = REPO_ROOT / "src" / "ontology" / "uberon-odk.yaml"
ONTOLOGY_DIR = REPO_ROOT / "src" / "ontology"


def discover_templates(name: str) -> list[Path]:
    """Return template TSVs whose stem starts with `<name>` (excludes -reports dirs)."""
    files = sorted(TEMPLATE_DIR.glob(f"{name}*.template.tsv"))
    return [f for f in files if f.is_file()]


def component_filename(template_path: Path) -> str:
    """Map `hra-muscular-groups.template.tsv` → `hra_muscular_groups.owl`."""
    stem = template_path.name[: -len(".template.tsv")]
    return stem.replace("-", "_") + ".owl"


def already_registered(yaml_text: str, component: str) -> bool:
    # Match `    - filename: <component>` exactly on a line.
    return f"- filename: {component}\n" in yaml_text


def build_entry(component: str, template_filename: str) -> str:
    return (
        f"    - filename: {component}\n"
        f"      use_template: true\n"
        f"      templates:\n"
        f"        - {template_filename}\n"
    )


def insert_entries(yaml_text: str, entries: list[str]) -> str:
    """Insert entries at the end of components.products: (before `workflows:`)."""
    marker = "\nworkflows:"
    idx = yaml_text.find(marker)
    if idx < 0:
        raise RuntimeError("Could not find `workflows:` section in uberon-odk.yaml")
    return yaml_text[:idx] + "".join(entries) + yaml_text[idx:]


def register(name: str) -> list[Path]:
    templates = discover_templates(name)
    if not templates:
        print(f"No templates found matching src/templates/{name}*.template.tsv",
              file=sys.stderr)
        sys.exit(1)

    yaml_text = ODK_YAML.read_text()
    new_entries: list[str] = []
    registered: list[Path] = []
    skipped: list[Path] = []

    for tpl in templates:
        component = component_filename(tpl)
        if already_registered(yaml_text, component):
            skipped.append(tpl)
            continue
        new_entries.append(build_entry(component, tpl.name))
        registered.append(tpl)

    if new_entries:
        ODK_YAML.write_text(insert_entries(yaml_text, new_entries))
        print(f"Registered {len(registered)} template(s) in {ODK_YAML.relative_to(REPO_ROOT)}:")
        for tpl in registered:
            print(f"  + {component_filename(tpl)}  ←  {tpl.name}")
    else:
        print("All matching templates already registered in uberon-odk.yaml.")

    if skipped:
        print(f"Skipped {len(skipped)} already-registered template(s):")
        for tpl in skipped:
            print(f"  = {component_filename(tpl)}  ←  {tpl.name}")

    return registered


def run_update_repo() -> None:
    print("\nRunning `sh run.sh make update_repo` (this may take several minutes)...")
    result = subprocess.run(
        ["sh", "run.sh", "make", "update_repo"],
        cwd=ONTOLOGY_DIR,
    )
    if result.returncode != 0:
        sys.exit(f"update_repo failed with exit code {result.returncode}")
    print("update_repo completed successfully.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--name",
        required=True,
        help="Base name used by Stage 4 (e.g. hra-muscular).",
    )
    parser.add_argument(
        "--skip-update-repo",
        action="store_true",
        help="Edit uberon-odk.yaml but skip the ODK Makefile regeneration step.",
    )
    args = parser.parse_args()

    registered = register(args.name)

    if args.skip_update_repo:
        if registered:
            print("\nSkipping update_repo (per --skip-update-repo).")
            print("Run `sh run.sh make update_repo` from src/ontology/ to wire components into the Makefile.")
        return

    if not registered:
        print("\nNothing changed — skipping update_repo.")
        return

    run_update_repo()


if __name__ == "__main__":
    main()
