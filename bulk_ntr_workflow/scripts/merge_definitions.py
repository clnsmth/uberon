"""
Stage 4: Merge subagent outputs back into the ROBOT template TSV.

Reads all bulk_ntr_workflow/outputs/definitions/*.json files (excluding input/ subdir).
Each JSON may contain:
  - "definitions":             {label: definition_string}
  - "wikipedia_images":        {label: image_url}
  - "resolved_relationships":  {label: "is_a" | "part_of"}
  - "confirmed_matches":       [{label, uberon_id, confidence}]
  - "possible_matches":        [{label, uberon_id, confidence, note}]
  - "resolved_parents":        {label: "UBERON:xxxxxxx"}  (for FMA/ASCTB-TEMP rows)

Reads the working template from bulk_ntr_workflow/outputs/template_initial.tsv.
Writes the final template back to src/templates/<name>.template.tsv (in-place update).
Appends confirmed/possible matches to src/templates/<name>-reports/candidates.tsv.

Requires --name matching the value used in Stage 1.

Usage:
  uv run scripts/merge_definitions.py --name hra-muscular
"""

import argparse
import csv
import json
import re
from pathlib import Path

NTR_ROOT    = Path(__file__).resolve().parent.parent
REPO_ROOT   = NTR_ROOT.parent
INPUT_TSV   = NTR_ROOT / "outputs" / "template_initial.tsv"
DEFS_DIR    = NTR_ROOT / "outputs" / "definitions"

PENDING_PATTERN = re.compile(r'^\[PENDING\]$')
INFER_PATTERN   = re.compile(r'^INFER')

# Column indices
COL_ID      = 0
COL_LABEL   = 1
COL_DEF     = 2
COL_XREF    = 3
COL_IS_A    = 4
COL_PART_OF = 5
COL_IMAGE   = 10  # Wikipedia_image
COL_TERMREF = 11  # xref (direct oboInOwl:hasDbXref on term)


def _normalise_matches(raw: list) -> list:
    """Normalise various field-name conventions agents may use into {label, uberon_id, ...}."""
    out = []
    for m in raw:
        label = m.get("label") or m.get("ntr_label") or m.get("term_label", "")
        uid   = m.get("uberon_id") or m.get("matched_id") or ""
        out.append({
            "label":      label,
            "uberon_id":  uid,
            "confidence": m.get("confidence", ""),
            "note":       m.get("note", ""),
        })
    return out


def load_subagent_outputs() -> dict:
    """Load and merge all subagent JSON outputs into a dict of merged maps/lists."""
    out = {
        "definitions":      {},
        "images":           {},
        "relationships":    {},
        "resolved_parents": {},
        "xrefs":            {},   # label → pipe-sep xref string (Wikipedia URL + FMA ID)
        "def_xrefs_extra":  {},   # label → pipe-sep PMIDs/DOIs to append to def_xref column
        "confirmed":        [],
        "possible":         [],
        "out_of_scope":     [],   # [{label, reason, suggestion}]
        "name_corrections": [],   # [{label, suggested, reason}]
    }

    for jf in sorted(DEFS_DIR.glob("*.json")):
        with open(jf, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            print(f"  WARNING: {jf.name} is not a dict, skipping")
            continue

        out["definitions"].update(data.get("definitions", {}))
        out["images"].update(data.get("wikipedia_images", {}))
        out["relationships"].update(data.get("resolved_relationships", {}))
        out["resolved_parents"].update(data.get("resolved_parents", {}))
        out["xrefs"].update(data.get("xrefs", {}))
        out["def_xrefs_extra"].update(data.get("def_xrefs_to_add", {}))
        out["confirmed"].extend(_normalise_matches(data.get("confirmed_matches", [])))
        out["possible"].extend(_normalise_matches(data.get("possible_matches", [])))
        out["out_of_scope"].extend(data.get("out_of_scope", []))
        out["name_corrections"].extend(data.get("name_corrections", []))
        # Also accept {label: {match_type, matched_id, ...}} dict form
        for lbl, info in data.get("existing_term_match", {}).items():
            mt = info.get("match_type", "")
            entry = {
                "label":      lbl,
                "uberon_id":  info.get("matched_id") or info.get("uberon_id", ""),
                "confidence": info.get("confidence", "high" if "confirmed" in mt else "medium"),
                "note":       info.get("note", ""),
            }
            if "confirmed" in mt:
                out["confirmed"].append(entry)
            elif "possible" in mt:
                out["possible"].append(entry)

    return out


def extract_parent_id(cell_val: str) -> str:
    """Pull the embedded UBERON ID from INFER:, NEEDS_MAPPING:, etc."""
    m = re.match(r'^INFER:(UBERON:\d{7})$', cell_val)
    if m:
        return m.group(1)
    m = re.match(r'^(UBERON:\d{7})$', cell_val)
    if m:
        return m.group(1)
    m = re.match(r'^NEEDS_MAPPING:(.*)', cell_val)
    if m:
        return m.group(1)
    return ""


def process(name: str) -> None:
    templates_dir       = REPO_ROOT / "src" / "templates"
    final_tsv           = templates_dir / f"{name}.template.tsv"
    reports_dir         = templates_dir / f"{name}-reports"
    candidates_tsv      = reports_dir / "candidates.tsv"
    out_of_scope_tsv    = reports_dir / "out_of_scope.tsv"
    name_corrections_tsv = reports_dir / "name_corrections.tsv"

    if not INPUT_TSV.exists():
        raise FileNotFoundError(f"Input not found: {INPUT_TSV}\nRun generate_template.py first.")
    if not final_tsv.exists():
        raise FileNotFoundError(
            f"Template not found: {final_tsv}\nRun generate_template.py --name {name} first."
        )

    sub = load_subagent_outputs()
    print(f"Loaded: {len(sub['definitions'])} definitions, {len(sub['images'])} images, "
          f"{len(sub['relationships'])} resolved relationships, "
          f"{len(sub['resolved_parents'])} resolved parents, {len(sub['xrefs'])} xrefs, "
          f"{len(sub['def_xrefs_extra'])} extra def_xrefs, "
          f"{len(sub['confirmed'])} confirmed matches, {len(sub['possible'])} possible matches, "
          f"{len(sub['out_of_scope'])} out-of-scope, "
          f"{len(sub['name_corrections'])} name corrections")

    # Map source label → corrected label (one direction only)
    name_correction_map = {
        nc["label"]: nc.get("suggested", "").strip()
        for nc in sub["name_corrections"] if nc.get("suggested", "").strip()
    }

    rows = []
    updated_defs       = 0
    updated_images     = 0
    updated_rels       = 0
    updated_xrefs      = 0
    updated_def_xrefs  = 0
    relabelled         = 0
    still_pending      = 0
    still_infer        = 0
    still_unknown_rel: list[str] = []
    excluded_labels: set[str] = {m["label"] for m in sub["confirmed"]}
    out_of_scope_labels: set[str] = {o["label"] for o in sub["out_of_scope"]}

    with open(INPUT_TSV, newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        header_row    = next(reader)
        directive_row = next(reader)
        rows.append(header_row)
        rows.append(directive_row)

        for row in reader:
            if not row:
                rows.append(row)
                continue

            while len(row) <= COL_IMAGE:
                row.append("")

            label = row[COL_LABEL].strip()

            # Exclude confirmed-match terms from template
            if label in excluded_labels:
                continue

            # Exclude out-of-scope (pathological/dysfunctional) terms; logged separately
            if label in out_of_scope_labels:
                continue

            # Apply name correction (curator-reviewable)
            if label in name_correction_map:
                row[COL_LABEL] = name_correction_map[label]
                relabelled += 1
                # Subagent keys may use either source or corrected label; check both below

            def get_for_label(d: dict):
                """Lookup using corrected label or original — agent may key by either."""
                return d.get(name_correction_map.get(label, label)) or d.get(label)

            # Merge definition
            new_def = get_for_label(sub["definitions"])
            if new_def and new_def.strip():
                row[COL_DEF] = new_def.strip()
                updated_defs += 1

            # Merge Wikipedia image
            new_img = get_for_label(sub["images"])
            if new_img and new_img.strip():
                row[COL_IMAGE] = new_img.strip()
                updated_images += 1

            # Merge direct xrefs (Wikipedia URL + FMA ID) — append to any pre-populated value
            while len(row) <= COL_TERMREF:
                row.append("")
            new_xref = get_for_label(sub["xrefs"])
            if new_xref and new_xref.strip():
                existing = row[COL_TERMREF].strip()
                if existing:
                    parts = [p for p in existing.split("|") if p]
                    for p in new_xref.strip().split("|"):
                        if p and p not in parts:
                            parts.append(p)
                    row[COL_TERMREF] = "|".join(parts)
                else:
                    row[COL_TERMREF] = new_xref.strip()
                updated_xrefs += 1

            # Append literature references (PMID/DOI) to def_xref column
            extra_def_xref = get_for_label(sub["def_xrefs_extra"])
            if extra_def_xref and extra_def_xref.strip():
                existing = row[COL_XREF].strip()
                parts = [p for p in existing.split("|") if p]
                for p in extra_def_xref.strip().split("|"):
                    if p and p not in parts:
                        parts.append(p)
                row[COL_XREF] = "|".join(parts)
                updated_def_xrefs += 1

            # Merge resolved relationships + resolved parents
            is_a_val    = row[COL_IS_A].strip()
            part_of_val = row[COL_PART_OF].strip()

            parent_id = (get_for_label(sub["resolved_parents"]) or
                         extract_parent_id(is_a_val) or
                         extract_parent_id(part_of_val))

            rel = get_for_label(sub["relationships"])
            if rel and parent_id:
                if rel == "is_a":
                    row[COL_IS_A]    = parent_id
                    row[COL_PART_OF] = ""
                elif rel == "part_of":
                    row[COL_IS_A]    = ""
                    row[COL_PART_OF] = parent_id
                updated_rels += 1
            elif parent_id and (is_a_val.startswith("INFER:") or
                                is_a_val.startswith("UNRESOLVABLE:") or
                                is_a_val.startswith("NEEDS_MAPPING:")):
                # Subagent resolved parent but not relationship type — leave blank for curator
                row[COL_IS_A]    = ""
                row[COL_PART_OF] = ""
                still_unknown_rel.append(row[COL_LABEL].strip())

            # Count remaining issues
            if PENDING_PATTERN.match(row[COL_DEF].strip()):
                still_pending += 1
            if INFER_PATTERN.match(row[COL_IS_A].strip()) or \
               INFER_PATTERN.match(row[COL_PART_OF].strip()):
                still_infer += 1

            rows.append(row)

    # Write final template in-place to src/templates/
    with open(final_tsv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerows(rows)

    data_rows = len(rows) - 2
    print(f"\nUpdated template → {final_tsv}  ({data_rows} data rows)")
    print(f"  Definitions updated:        {updated_defs}")
    print(f"  Images added:               {updated_images}")
    print(f"  Xrefs added:                {updated_xrefs}")
    print(f"  def_xref refs appended:     {updated_def_xrefs}")
    print(f"  Labels corrected:           {relabelled}")
    print(f"  Relationships resolved:     {updated_rels}")
    print(f"  Still [PENDING] defs:       {still_pending}")
    print(f"  Still INFER relationships:  {still_infer}")
    print(f"  Relationship unresolved:    {len(still_unknown_rel)}")
    if still_unknown_rel:
        for lbl in still_unknown_rel:
            print(f"    ⚠ {lbl}")
    print(f"  Excluded (confirmed match): {len(excluded_labels)}")
    print(f"  Excluded (out_of_scope):    {len(out_of_scope_labels)}")

    # Append confirmed/possible matches to candidates.tsv
    if sub["confirmed"] or sub["possible"]:
        reports_dir.mkdir(parents=True, exist_ok=True)
        existing_rows = []
        existing_header = ["label", "as_iri", "uberon_id", "note"]
        if candidates_tsv.exists():
            with open(candidates_tsv, newline="", encoding="utf-8") as f:
                rows_read = list(csv.reader(f, delimiter="\t"))
                if rows_read:
                    existing_header = rows_read[0]
                    existing_rows = rows_read[1:]

        new_rows = []
        for m in sub["confirmed"]:
            new_rows.append([
                m.get("label", ""), "",
                m.get("uberon_id", ""),
                f"confirmed_match (confidence: {m.get('confidence','')})"
            ])
        for m in sub["possible"]:
            new_rows.append([
                m.get("label", ""), "",
                m.get("uberon_id", ""),
                f"possible_match ({m.get('note','')})"
            ])

        with open(candidates_tsv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(existing_header)
            writer.writerows(existing_rows)
            writer.writerows(new_rows)
        print(f"  Updated candidates.tsv   → {candidates_tsv}")

    # Out-of-scope report (pathological/dysfunctional terms — curator decides)
    if sub["out_of_scope"]:
        reports_dir.mkdir(parents=True, exist_ok=True)
        with open(out_of_scope_tsv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(["label", "reason", "suggestion"])
            for o in sub["out_of_scope"]:
                writer.writerow([
                    o.get("label", ""),
                    o.get("reason", ""),
                    o.get("suggestion", ""),
                ])
        print(f"  Wrote out_of_scope.tsv    → {out_of_scope_tsv}")

    # Name corrections report (so curator can review label changes)
    if sub["name_corrections"]:
        reports_dir.mkdir(parents=True, exist_ok=True)
        with open(name_corrections_tsv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(["source_label", "corrected_label", "reason"])
            for nc in sub["name_corrections"]:
                writer.writerow([
                    nc.get("label", ""),
                    nc.get("suggested", ""),
                    nc.get("reason", ""),
                ])
        print(f"  Wrote name_corrections.tsv → {name_corrections_tsv}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge subagent definition outputs into the ROBOT template"
    )
    parser.add_argument(
        "--name", required=True,
        help="Template name used in Stage 1 (e.g. 'hra-muscular')"
    )
    args = parser.parse_args()
    process(args.name)


if __name__ == "__main__":
    main()
