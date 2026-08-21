"""
PackEat Taxonomy Mapping & Alignment Tool.

Compares PackEat taxonomy/variety CSV records against Fruvia canonical taxonomy
(configs/taxonomy.yaml) to identify exact matches, alias matches, normalized
matches, and unmapped classes.

Generates:
1. Mapping JSON/YAML dictionary for ingest pipelines.
2. Markdown alignment report with coverage statistics.

USAGE:
    python scripts/build_packeat_taxonomy_mapping.py \\
        --packeat-taxonomy path/to/taxonomy.csv \\
        --variety-csv path/to/variety_classification.csv \\
        --output-mapping configs/packeat_mapping.json \\
        --output-report reports/packeat_alignment_report.md \\
        --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

from app.utils.file_utils import load_yaml_config


def normalize_label(label: str) -> str:
    """Normalize string to slug format (lowercase, underscores)."""
    if not label:
        return ""
    clean = re.sub(r"[_\-\s]+", " ", str(label).lower()).strip()
    clean = re.sub(r"\s+\d+$", "", clean).strip()  # Strip trailing variant numbers
    return clean.replace(" ", "_")


def build_taxonomy_index(taxonomy_yaml_path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """
    Build index of canonical classes and alias lookup dictionary.
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


def match_label(
    label: str,
    canonical_items: dict[str, dict[str, Any]],
    alias_map: dict[str, str],
) -> tuple[str, str | None, str]:
    """
    Attempt to match a raw label against the canonical taxonomy index.
    Returns: (match_status, canonical_class, match_reason)
    Match statuses: EXACT_MATCH | ALIAS_MATCH | NORM_MATCH | UNMAPPED
    """
    if not label or not label.strip():
        return "UNMAPPED", None, "Empty label"

    raw_clean = label.strip().lower()
    norm_clean = normalize_label(raw_clean)

    # 1. Exact match with canonical class
    if raw_clean in canonical_items:
        return "EXACT_MATCH", raw_clean, f"Exact match with canonical key '{raw_clean}'"

    # 2. Match in alias map
    if raw_clean in alias_map:
        canon = alias_map[raw_clean]
        return "ALIAS_MATCH", canon, f"Matches registered alias for '{canon}'"

    # 3. Normalized slug match
    if norm_clean in alias_map:
        canon = alias_map[norm_clean]
        return "NORM_MATCH", canon, f"Matches normalized slug '{norm_clean}' -> '{canon}'"

    # 4. Partial substring heuristics
    for canon_key in canonical_items:
        canon_norm = canon_key.replace("_", " ")
        if norm_clean.replace("_", " ").startswith(canon_norm):
            return "NORM_MATCH", canon_key, f"Prefix heuristic match with '{canon_key}'"

    return "UNMAPPED", None, "No match found in current taxonomy.yaml"


def parse_csv_labels(csv_path: Path) -> list[dict[str, str]]:
    """Parse labels and metadata from a given CSV file."""
    if not csv_path.exists():
        return []

    records: list[dict[str, str]] = []
    with open(csv_path, encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append({k.strip(): (v.strip() if v else "") for k, v in row.items()})
    return records


def analyze_packeat(
    packeat_taxonomy_path: Path | None,
    variety_csv_path: Path | None,
    canonical_items: dict[str, dict[str, Any]],
    alias_map: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Analyze PackEat records and produce mapping and alignment results.
    """
    results: list[dict[str, Any]] = []
    mapping: dict[str, str] = {}

    labels_to_evaluate: set[str] = set()

    if packeat_taxonomy_path and packeat_taxonomy_path.exists():
        records = parse_csv_labels(packeat_taxonomy_path)
        for r in records:
            for field in ["label", "class", "name", "species", "fruit", "category"]:
                if field in r and r[field]:
                    labels_to_evaluate.add(r[field])

    if variety_csv_path and variety_csv_path.exists():
        records = parse_csv_labels(variety_csv_path)
        for r in records:
            for field in ["variety", "label", "class_name", "name"]:
                if field in r and r[field]:
                    labels_to_evaluate.add(r[field])

    # If no files provided, evaluate sample placeholder list or empty
    if not labels_to_evaluate:
        print("[INFO] No external PackEat CSV files found/provided. Generating empty baseline alignment.")

    for label in sorted(labels_to_evaluate):
        status, canon, reason = match_label(label, canonical_items, alias_map)
        item_entry = {
            "source_label": label,
            "status": status,
            "canonical_class": canon,
            "reason": reason,
        }
        if canon:
            mapping[label] = canon
        results.append(item_entry)

    return mapping, results


def generate_markdown_report(
    results: list[dict[str, Any]],
    canonical_count: int,
    output_path: Path | None,
) -> str:
    """Generate Markdown alignment summary report."""
    total = len(results)
    exact = sum(1 for r in results if r["status"] == "EXACT_MATCH")
    alias = sum(1 for r in results if r["status"] == "ALIAS_MATCH")
    norm = sum(1 for r in results if r["status"] == "NORM_MATCH")
    unmapped = sum(1 for r in results if r["status"] == "UNMAPPED")

    mapped = exact + alias + norm
    coverage_pct = (mapped / total * 100) if total > 0 else 0.0

    lines = [
        "# PackEat Dataset Taxonomy Alignment Report",
        "",
        "## Summary Statistics",
        f"- **Canonical Taxonomy Species**: {canonical_count}",
        f"- **Evaluated Source Labels**: {total}",
        f"- **Mapped Labels**: {mapped} ({coverage_pct:.1f}%)",
        f"  - **Exact Matches**: {exact}",
        f"  - **Alias Matches**: {alias}",
        f"  - **Normalized Heuristic Matches**: {norm}",
        f"- **Unmapped Labels (Action Required)**: {unmapped}",
        "",
        "## Alignment Details",
        "| Source Label | Match Status | Canonical Class | Notes |",
        "| :--- | :--- | :--- | :--- |",
    ]

    for r in results:
        canon_display = r["canonical_class"] or "*None*"
        lines.append(f"| `{r['source_label']}` | **{r['status']}** | `{canon_display}` | {r['reason']} |")

    content = "\n".join(lines) + "\n"

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[REPORT] Report written to: {output_path}")

    return content


def main() -> None:
    parser = argparse.ArgumentParser(description="PackEat Taxonomy Mapping and Alignment Tool")
    parser.add_argument("--packeat-taxonomy", type=Path, default=None, help="Path to PackEat taxonomy.csv")
    parser.add_argument("--variety-csv", type=Path, default=None, help="Path to PackEat variety_classification.csv")
    parser.add_argument("--taxonomy-yaml", type=Path, default=Path("configs/taxonomy.yaml"), help="Path to configs/taxonomy.yaml")
    parser.add_argument("--output-mapping", type=Path, default=Path("configs/packeat_mapping.json"), help="Output JSON mapping path")
    parser.add_argument("--output-report", type=Path, default=Path("reports/packeat_alignment_report.md"), help="Output Markdown report path")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Perform dry-run without writing output files")

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

        mapping, results = analyze_packeat(
            args.packeat_taxonomy,
            args.variety_csv,
            canonical_items,
            alias_map,
        )

        if not args.dry_run and results:
            args.output_mapping.parent.mkdir(parents=True, exist_ok=True)
            with open(args.output_mapping, "w", encoding="utf-8") as f:
                json.dump(mapping, f, indent=2, ensure_ascii=False)
            print(f"[SUCCESS] Mapping saved to {args.output_mapping}")

            generate_markdown_report(results, len(canonical_items), args.output_report)
        else:
            report_text = generate_markdown_report(results, len(canonical_items), None)
            if args.dry_run:
                print("\n[DRY-RUN OUTPUT]")
                print(report_text[:1000] + ("\n..." if len(report_text) > 1000 else ""))

    except Exception as e:
        print(f"[ERROR] Failed to run taxonomy mapping: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
