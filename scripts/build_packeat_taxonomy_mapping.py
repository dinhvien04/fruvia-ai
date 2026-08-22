"""
PackEat Taxonomy Mapping & Alignment Tool.

Parses structured PackEat CSV datasets (e.g. taxonomy.csv, variety_classification.csv),
validates known schema headers, aligns varieties/species against Fruvia canonical taxonomy
(configs/taxonomy.yaml), and generates an approved mapping dictionary and Markdown alignment report.

Output mapping format contains ONLY high-confidence matches:
- EXACT
- ALIAS
- NORMALIZED_EXACT

Never automatically approves MANUAL_REVIEW, UNMATCHED, prefix, or heuristic matches.

USAGE:
    python scripts/build_packeat_taxonomy_mapping.py \\
        --packeat-taxonomy path/to/taxonomy.csv \\
        --variety-csv path/to/variety_classification.csv \\
        --output-mapping configs/packeat_mapping.json \\
        --output-report reports/packeat_alignment_report.md
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Ensure backend directory is in sys.path when running scripts standalone
if str(Path(__file__).resolve().parent.parent / "backend") not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.utils.file_utils import load_yaml_config  # noqa: E402


@dataclass
class PackEatRecord:
    """Structured record model for PackEat biological taxonomy items."""

    raw_label: str
    variety: str | None
    species: str | None
    source: str = "packeat"
    taxonomy_row: dict[str, str] | None = None
    variety_row: dict[str, str] | None = None


def normalize_label(label: str) -> str:
    """Normalize string to slug format (lowercase, punctuation/spaces replaced by underscore)."""
    if not label:
        return ""
    clean = re.sub(r"[_\-\s]+", " ", str(label).lower()).strip()
    return clean.replace(" ", "_")


def build_taxonomy_index(
    taxonomy_yaml_path: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """
    Build index of canonical classes and alias lookup dictionary from configs/taxonomy.yaml.
    Returns: (canonical_items, alias_to_canonical_map)
    """
    if not taxonomy_yaml_path.exists():
        raise FileNotFoundError(f"Taxonomy file not found at {taxonomy_yaml_path}")

    data = load_yaml_config(taxonomy_yaml_path)
    taxonomy_dict = data.get("taxonomy", {}) if isinstance(data, dict) else {}

    canonical_items: dict[str, dict[str, Any]] = {}
    alias_map: dict[str, str] = {}

    for key, val in taxonomy_dict.items():
        if not isinstance(val, dict):
            continue
        canonical_items[key] = val
        alias_map[key.lower()] = key
        alias_map[normalize_label(key)] = key

        # Index aliases
        for alias in val.get("aliases", []):
            alias_str = str(alias).strip().lower()
            if alias_str:
                alias_map[alias_str] = key
                alias_map[normalize_label(alias_str)] = key

    return canonical_items, alias_map


def match_packeat_record(
    record: PackEatRecord,
    canonical_items: dict[str, dict[str, Any]],
    alias_map: dict[str, str],
) -> tuple[str, str | None, str]:
    """
    Strict alignment of PackEat structured record against canonical taxonomy.
    Priority:
    1. Exact match on composite species+variety or raw_label or species or variety.
    2. Registered alias match.
    3. Normalized exact match.
    4. Numeric suffix variety check -> Flagged as MANUAL_REVIEW (never auto-approved).
    5. Heuristic prefix -> Flagged as MANUAL_REVIEW (never auto-approved).
    6. UNMATCHED.
    """
    candidates: list[str] = []

    # Check for composite species + variety and apply explicit overrides
    if record.species and record.variety:
        s = record.species.strip()
        v = record.variety.strip()
        # Explicit override: ("apple", "granny") -> ("apple", "granny_smith")
        if s.lower() == "apple" and v.lower() == "granny":
            v = "granny_smith"
            candidates.append(f"{s}_{v}")
            candidates.append(f"{s} {v}")
            candidates.append(v)
        else:
            candidates.append(f"{s}_{v}")
            candidates.append(f"{s} {v}")

    for c in [record.raw_label, record.variety, record.species]:
        if c and str(c).strip() and str(c).strip() not in candidates:
            candidates.append(str(c).strip())

    if not candidates:
        return "UNMATCHED", None, "No valid label or species in record"

    if record.taxonomy_row and record.taxonomy_row.get("_ambiguous_join") == "true":
        return (
            "MANUAL_REVIEW",
            None,
            f"Ambiguous 1-to-many join ({record.taxonomy_row.get('_match_count')} taxonomy rows matched) for candidates {candidates}",
        )

    # 1. Exact match
    for cand in candidates:
        cand_clean = cand.strip().lower()
        if cand_clean in canonical_items:
            return "EXACT", cand_clean, f"Exact match on '{cand}'"

    # 2. Registered alias match
    for cand in candidates:
        cand_clean = cand.strip().lower()
        if cand_clean in alias_map:
            canon = alias_map[cand_clean]
            return "ALIAS", canon, f"Alias match for '{canon}' from candidate '{cand}'"

    # 3. Normalized exact match (without numeric stripping)
    for cand in candidates:
        norm = normalize_label(cand)
        if norm in alias_map:
            canon = alias_map[norm]
            return "NORMALIZED_EXACT", canon, f"Normalized match for '{canon}' from '{cand}'"

    # 4. Numeric variety suffix check (e.g. 'Apple 1', 'Banana 2') -> MANUAL_REVIEW only
    for cand in candidates:
        cand_str = cand.strip()
        if re.search(r"[\s_]\d+$", cand_str):
            base_stripped = re.sub(r"[\s_]\d+$", "", cand_str).strip()
            norm_base = normalize_label(base_stripped)
            if norm_base in alias_map:
                canon = alias_map[norm_base]
                return (
                    "MANUAL_REVIEW",
                    canon,
                    f"Numeric variety suffix in candidate '{cand}' -> possible base '{canon}' (requires human verification)",
                )

    # 5. Prefix heuristic check -> MANUAL_REVIEW only
    for cand in candidates:
        norm = normalize_label(cand)
        for canon_key in canonical_items:
            canon_norm = canon_key.replace("_", " ")
            if norm.replace("_", " ").startswith(canon_norm):
                return (
                    "MANUAL_REVIEW",
                    canon_key,
                    f"Prefix match '{cand}' -> '{canon_key}' (requires human verification)",
                )

    return "UNMATCHED", None, f"No match found for candidates: {candidates}"


def parse_packeat_csvs(
    taxonomy_csv_path: Path | None,
    variety_csv_path: Path | None,
) -> list[PackEatRecord]:
    """
    Parse PackEat CSV files into structured PackEatRecord objects.
    Validates headers fail-closed against known schemas.
    """
    records: list[PackEatRecord] = []

    # Valid recognized schemas for PackEat taxonomy & variety CSVs
    valid_tax_headers = {
        "species",
        "label",
        "class",
        "fruit",
        "name",
        "id",
        "code",
        "common name",
        "common_name",
        "common variety",
        "common_variety",
    }
    valid_var_headers = {
        "variety",
        "label",
        "species",
        "name",
        "variety_name",
        "class_name",
        "common name",
        "common_name",
        "common variety",
        "common_variety",
    }

    tax_rows: dict[str, list[dict[str, str]]] = {}
    if taxonomy_csv_path and taxonomy_csv_path.exists():
        with open(taxonomy_csv_path, encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f)
            fieldnames = [h.strip() for h in (reader.fieldnames or []) if h]
            headers = set(h.lower() for h in fieldnames)
            if not headers.intersection(valid_tax_headers):
                raise ValueError(
                    f"Unsupported PackEat CSV schema in '{taxonomy_csv_path}'. Detected columns: {reader.fieldnames}"
                )
            for row in reader:
                cleaned_row = {
                    k.strip().lower(): (v.strip() if v else "")
                    for k, v in row.items()
                    if k is not None
                }
                # Extract species and variety if present in taxonomy row
                spec = (
                    cleaned_row.get("species")
                    or cleaned_row.get("common name")
                    or cleaned_row.get("common_name")
                    or cleaned_row.get("fruit")
                    or cleaned_row.get("name")
                    or cleaned_row.get("label")
                )
                var = (
                    cleaned_row.get("variety")
                    or cleaned_row.get("common variety")
                    or cleaned_row.get("common_variety")
                    or cleaned_row.get("variety_name")
                )
                row_id = cleaned_row.get("id") or cleaned_row.get("code")

                # Index by composite key (species_variety)
                if spec and var:
                    comp_key = f"{spec.lower().strip()}_{var.lower().strip()}"
                    tax_rows.setdefault(comp_key, []).append(cleaned_row)

                # Index by species/label
                if spec:
                    tax_rows.setdefault(spec.lower().strip(), []).append(cleaned_row)

                # Index by ID/code
                if row_id:
                    tax_rows.setdefault(row_id.lower().strip(), []).append(cleaned_row)

    if variety_csv_path and variety_csv_path.exists():
        with open(variety_csv_path, encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f)
            fieldnames = [h.strip() for h in (reader.fieldnames or []) if h]
            headers = set(h.lower() for h in fieldnames)
            if not headers.intersection(valid_var_headers):
                raise ValueError(
                    f"Unsupported PackEat CSV schema in '{variety_csv_path}'. Detected columns: {reader.fieldnames}"
                )
            for row in reader:
                cleaned_row = {
                    k.strip().lower(): (v.strip() if v else "")
                    for k, v in row.items()
                    if k is not None
                }
                raw_label = (
                    cleaned_row.get("label")
                    or cleaned_row.get("variety")
                    or cleaned_row.get("common variety")
                    or cleaned_row.get("common_variety")
                    or cleaned_row.get("class_name")
                    or cleaned_row.get("name")
                    or "unknown"
                )
                variety_val = (
                    cleaned_row.get("variety")
                    or cleaned_row.get("common variety")
                    or cleaned_row.get("common_variety")
                    or cleaned_row.get("variety_name")
                )
                species_val = (
                    cleaned_row.get("species")
                    or cleaned_row.get("common name")
                    or cleaned_row.get("common_name")
                    or cleaned_row.get("fruit")
                )

                # Attempt composite key match (species, variety) or single key join
                matched_tax_rows = []
                if species_val and variety_val:
                    composite_key = f"{species_val.lower().strip()}_{variety_val.lower().strip()}"
                    if composite_key in tax_rows:
                        matched_tax_rows = tax_rows[composite_key]
                if not matched_tax_rows and species_val and species_val.lower().strip() in tax_rows:
                    matched_tax_rows = tax_rows[species_val.lower().strip()]
                elif not matched_tax_rows and raw_label.lower().strip() in tax_rows:
                    matched_tax_rows = tax_rows[raw_label.lower().strip()]

                # Fail-safe: If join is ambiguous (multiple matching taxonomy entries), flag for manual review
                is_ambiguous = len(matched_tax_rows) > 1
                matched_tax_row = matched_tax_rows[0] if matched_tax_rows else None
                if is_ambiguous:
                    matched_tax_row = {
                        **(matched_tax_row or {}),
                        "_ambiguous_join": "true",
                        "_match_count": str(len(matched_tax_rows)),
                    }

                records.append(
                    PackEatRecord(
                        raw_label=raw_label,
                        variety=variety_val,
                        species=species_val,
                        source="packeat",
                        taxonomy_row=matched_tax_row,
                        variety_row=cleaned_row,
                    )
                )

    # If only taxonomy CSV was provided
    elif taxonomy_csv_path and taxonomy_csv_path.exists():
        for key, row_list in tax_rows.items():
            for row in row_list:
                raw_label = row.get("label") or row.get("species") or row.get("name") or key
                records.append(
                    PackEatRecord(
                        raw_label=raw_label,
                        variety=None,
                        species=row.get("species") or raw_label,
                        source="packeat",
                        taxonomy_row=row,
                        variety_row=None,
                    )
                )

    return records


def analyze_packeat_records(
    records: list[PackEatRecord],
    canonical_items: dict[str, dict[str, Any]],
    alias_map: dict[str, str],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """
    Align structured PackEat records against canonical taxonomy.
    Outputs:
    1. Approved mapping dictionary (EXACT, ALIAS, NORMALIZED_EXACT only).
    2. Detailed review list including MANUAL_REVIEW and UNMATCHED entries.
    """
    approved_mapping: dict[str, str] = {}
    review_entries: list[dict[str, Any]] = []

    for rec in records:
        status, canon, reason = match_packeat_record(rec, canonical_items, alias_map)
        entry = {
            "raw_label": rec.raw_label,
            "variety": rec.variety,
            "species": rec.species,
            "canonical_class": canon,
            "match_status": status,
            "match_reason": reason,
            "source": rec.source,
            "source_rows": {
                "taxonomy_row": rec.taxonomy_row,
                "variety_row": rec.variety_row,
            },
        }
        review_entries.append(entry)

        # Machine-approved mapping file may contain ONLY high-confidence matches to known canonical classes
        if canon and status in {"EXACT", "ALIAS", "NORMALIZED_EXACT"} and canon in canonical_items:
            approved_mapping[rec.raw_label] = canon
            if rec.variety:
                approved_mapping[rec.variety] = canon

    return approved_mapping, review_entries


def generate_markdown_report(
    review_entries: list[dict[str, Any]],
    canonical_count: int,
    output_path: Path | None,
) -> str:
    """Generate Markdown alignment summary report."""
    total = len(review_entries)
    exact = sum(1 for r in review_entries if r["match_status"] == "EXACT")
    alias = sum(1 for r in review_entries if r["match_status"] == "ALIAS")
    norm = sum(1 for r in review_entries if r["match_status"] == "NORMALIZED_EXACT")
    manual = sum(1 for r in review_entries if r["match_status"] == "MANUAL_REVIEW")
    unmatched = sum(1 for r in review_entries if r["match_status"] == "UNMATCHED")

    mapped = exact + alias + norm
    coverage_pct = (mapped / total * 100) if total > 0 else 0.0

    lines = [
        "# PackEat Dataset Taxonomy Alignment Report",
        "",
        "## Summary Statistics",
        f"- **Canonical Taxonomy Species**: {canonical_count}",
        f"- **Evaluated Source Records**: {total}",
        f"- **Auto-Approved Mappings**: {mapped} ({coverage_pct:.1f}%)",
        f"  - **Exact Matches**: {exact}",
        f"  - **Alias Matches**: {alias}",
        f"  - **Normalized Matches**: {norm}",
        f"- **Manual Review Required**: {manual}",
        f"- **Unmatched Records**: {unmatched}",
        "",
        "## Alignment Details",
        "| Raw Label | Variety | Species | Match Status | Canonical Class | Reason |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for r in review_entries:
        canon_display = r["canonical_class"] or "*None*"
        var_display = r["variety"] or "-"
        spec_display = r["species"] or "-"
        lines.append(
            f"| `{r['raw_label']}` | {var_display} | {spec_display} | **{r['match_status']}** | `{canon_display}` | {r['match_reason']} |"
        )

    content = "\n".join(lines) + "\n"

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[REPORT] Report written to: {output_path}")

    return content


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Structured PackEat Taxonomy Mapping & Alignment Tool"
    )
    parser.add_argument(
        "--packeat-taxonomy", type=Path, default=None, help="Path to PackEat taxonomy.csv"
    )
    parser.add_argument(
        "--variety-csv", type=Path, default=None, help="Path to PackEat variety_classification.csv"
    )
    parser.add_argument(
        "--taxonomy-yaml",
        type=Path,
        default=Path("configs/taxonomy.yaml"),
        help="Path to configs/taxonomy.yaml",
    )
    parser.add_argument(
        "--output-mapping",
        type=Path,
        default=Path("configs/packeat_mapping.json"),
        help="Output approved JSON mapping path",
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=Path("reports/packeat_alignment_report.md"),
        help="Output Markdown report path",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Perform dry-run without writing output files",
    )

    args = parser.parse_args()

    print("=== PackEat Taxonomy Alignment Tool ===")
    print(f"Taxonomy YAML : {args.taxonomy_yaml}")
    print(f"PackEat Tax   : {args.packeat_taxonomy}")
    print(f"Variety CSV   : {args.variety_csv}")
    print(f"Dry Run       : {args.dry_run}")
    print("-" * 50)

    try:
        canonical_items, alias_map = build_taxonomy_index(args.taxonomy_yaml)
        print(f"[OK] Loaded {len(canonical_items)} canonical species from taxonomy.yaml.")

        records = parse_packeat_csvs(args.packeat_taxonomy, args.variety_csv)
        print(f"[OK] Parsed {len(records)} structured PackEat records.")

        approved_mapping, review_entries = analyze_packeat_records(
            records, canonical_items, alias_map
        )

        if not args.dry_run and review_entries:
            args.output_mapping.parent.mkdir(parents=True, exist_ok=True)
            with open(args.output_mapping, "w", encoding="utf-8") as f:
                json.dump(approved_mapping, f, indent=2, ensure_ascii=False)
            print(
                f"[SUCCESS] Approved mapping ({len(approved_mapping)} entries) saved to {args.output_mapping}"
            )

            generate_markdown_report(review_entries, len(canonical_items), args.output_report)
        else:
            report_text = generate_markdown_report(review_entries, len(canonical_items), None)
            if args.dry_run:
                print("\n[DRY-RUN OUTPUT REPORT]")
                print(report_text[:1000] + ("\n..." if len(report_text) > 1000 else ""))

    except Exception as e:
        print(f"[ERROR] Failed to run taxonomy mapping: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
