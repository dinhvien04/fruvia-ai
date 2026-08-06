#!/usr/bin/env python3
"""
Fruvia AI — Validate Manifest

Validates an existing manifest CSV:
- Checks all required columns exist
- Verifies each image file exists on disk
- Validates image_id uniqueness
- Checks for orphaned records (file missing)
- Validates split labels
- Verifies target_class is in classes.yaml
- Reports per-split per-class counts

Usage:
    python scripts/validate_manifest.py \
        --manifest data/manifests/manifest.csv \
        --data-dir data/raw \
        --classes configs/classes.yaml
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set

import yaml

REQUIRED_COLUMNS = {
    "image_id",
    "original_class",
    "target_class",
    "relative_path",
    "filename",
    "width",
    "height",
    "file_size",
    "sha256",
    "split",
    "source",
    "is_valid",
}

VALID_SPLITS = {"train", "validation", "test", "gallery"}


def load_yaml(path: Path) -> dict:
    """Load a YAML config file."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_manifest(
    manifest_path: Path,
    data_dir: Path | None = None,
    classes_path: Path | None = None,
) -> Dict[str, Any]:
    """
    Validate a manifest CSV and return a validation report.

    Parameters
    ----------
    manifest_path : Path
        Path to the manifest CSV.
    data_dir : Path or None
        If given, verify each image file exists.
    classes_path : Path or None
        If given, verify each target_class is in classes.yaml.

    Returns
    -------
    dict
        Validation results with errors, warnings, and stats.
    """
    errors: List[str] = []
    warnings: List[str] = []

    # Load manifest
    with open(manifest_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        columns = set(reader.fieldnames or [])
        rows = list(reader)

    # Check columns
    missing_cols = REQUIRED_COLUMNS - columns
    if missing_cols:
        errors.append(f"Missing columns: {sorted(missing_cols)}")

    # Load valid classes if provided
    valid_classes: Set[str] | None = None
    if classes_path and classes_path.exists():
        cfg = load_yaml(classes_path)
        valid_classes = set(cfg.get("classes", []))

    # Validate rows
    image_ids: Set[str] = set()
    duplicate_ids: List[str] = []
    missing_files: List[str] = []
    invalid_splits: List[str] = []
    invalid_classes: List[str] = []
    split_counts: Counter = Counter()
    class_counts: Counter = Counter()
    per_split_per_class: Dict[str, Counter] = defaultdict(Counter)

    for i, row in enumerate(rows, start=2):  # header is line 1
        # Check image_id uniqueness
        iid = row.get("image_id", "")
        if iid in image_ids:
            duplicate_ids.append(f"Line {i}: {iid}")
        image_ids.add(iid)

        # Check split
        split = row.get("split", "")
        if split not in VALID_SPLITS:
            invalid_splits.append(f"Line {i}: split='{split}'")
        else:
            split_counts[split] += 1

        # Check target class
        tc = row.get("target_class", "")
        if valid_classes and tc not in valid_classes:
            invalid_classes.append(f"Line {i}: target_class='{tc}'")
        class_counts[tc] += 1
        if split:
            per_split_per_class[split][tc] += 1

        # Check file existence
        if data_dir:
            rel = row.get("relative_path", "")
            full_path = data_dir / rel
            if not full_path.exists():
                missing_files.append(rel)

    # Compile errors
    if duplicate_ids:
        errors.append(f"Duplicate image_ids: {len(duplicate_ids)}")
    if invalid_splits:
        errors.append(f"Invalid split values: {len(invalid_splits)}")
    if invalid_classes:
        warnings.append(f"Target classes not in classes.yaml: {len(invalid_classes)}")
    if missing_files:
        warnings.append(f"Files not found on disk: {len(missing_files)}")

    report: Dict[str, Any] = {
        "manifest_path": str(manifest_path),
        "total_rows": len(rows),
        "columns_present": sorted(columns),
        "columns_missing": sorted(missing_cols),
        "unique_image_ids": len(image_ids),
        "duplicate_image_ids": duplicate_ids[:20],
        "split_counts": dict(sorted(split_counts.items())),
        "class_counts": dict(sorted(class_counts.items())),
        "per_split_per_class": {
            k: dict(sorted(v.items())) for k, v in sorted(per_split_per_class.items())
        },
        "invalid_splits": invalid_splits[:20],
        "invalid_classes": invalid_classes[:20],
        "missing_files_count": len(missing_files),
        "missing_files_sample": missing_files[:10],
        "errors": errors,
        "warnings": warnings,
        "is_valid": len(errors) == 0,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Fruvia AI manifest CSV")
    parser.add_argument("--manifest", type=Path, required=True, help="Path to manifest CSV")
    parser.add_argument("--data-dir", type=Path, default=None, help="Raw data directory")
    parser.add_argument("--classes", type=Path, default=None, help="classes.yaml path")
    parser.add_argument("--output", type=Path, default=None, help="Output JSON report path")
    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"[ERROR] Manifest not found: {args.manifest}", file=sys.stderr)
        sys.exit(1)

    report = validate_manifest(
        manifest_path=args.manifest,
        data_dir=args.data_dir,
        classes_path=args.classes,
    )

    # Print summary
    print("\n" + "=" * 60)
    print("MANIFEST VALIDATION")
    print("=" * 60)
    print(f"  Total rows:        {report['total_rows']}")
    print(f"  Unique image IDs:  {report['unique_image_ids']}")
    print(f"  Valid:             {'YES' if report['is_valid'] else 'NO'}")
    print()

    if report["errors"]:
        print("ERRORS:")
        for err in report["errors"]:
            print(f"  - {err}")
        print()

    if report["warnings"]:
        print("WARNINGS:")
        for w in report["warnings"]:
            print(f"  - {w}")
        print()

    print("Split distribution:")
    for split, count in sorted(report["split_counts"].items()):
        print(f"  {split:15s}: {count}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\nReport saved to {args.output}")

    sys.exit(0 if report["is_valid"] else 1)


if __name__ == "__main__":
    main()
