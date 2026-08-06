#!/usr/bin/env python3
"""
Fruvia AI — Dataset Audit Script

Scans raw dataset directory and produces a comprehensive audit report:
- Total image count
- Per-class counts
- Corrupt / unreadable images
- Duplicate detection via SHA-256
- Classes not in mapping
- Classes with too few samples
- Exports JSON + CSV reports

Usage:
    python scripts/audit_dataset.py \
        --data-dir data/raw \
        --mapping configs/class_mapping.yaml \
        --output data/metadata/audit_report.json \
        --min-samples 20
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml
from PIL import Image

SUPPORTED_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}


def compute_sha256(filepath: Path, chunk_size: int = 65536) -> str:
    """Compute SHA-256 hex digest for a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def validate_image(filepath: Path) -> Tuple[bool, Optional[Tuple[int, int]]]:
    """
    Check if an image file can be opened and decoded by Pillow.

    Returns (is_valid, (width, height) or None).
    """
    try:
        with Image.open(filepath) as img:
            img.verify()
        # Re-open after verify to get size (verify invalidates the object)
        with Image.open(filepath) as img:
            return True, img.size
    except Exception:
        return False, None


def load_class_mapping(mapping_path: Path) -> Dict[str, str]:
    """Load original→target class mapping from YAML."""
    with open(mapping_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("class_mapping", {})


def discover_classes(data_dir: Path) -> List[str]:
    """
    Discover class folders inside a dataset directory.

    Assumes structure: data_dir/<split>/<class_folder>/images
    or data_dir/<class_folder>/images (flat).
    """
    classes: Set[str] = set()
    if not data_dir.exists():
        return sorted(classes)

    for item in data_dir.iterdir():
        if not item.is_dir():
            continue
        # Check if this is a split folder (Training, Test, etc.)
        sub_items = list(item.iterdir())
        has_subdirs = any(si.is_dir() for si in sub_items)
        has_images = any(
            si.is_file() and si.suffix.lower() in SUPPORTED_EXTENSIONS for si in sub_items
        )

        if has_subdirs and not has_images:
            # This is a split folder — class folders are inside
            for class_dir in item.iterdir():
                if class_dir.is_dir():
                    classes.add(class_dir.name)
        elif has_images:
            # This is directly a class folder
            classes.add(item.name)

    return sorted(classes)


def scan_images(data_dir: Path) -> List[Dict[str, Any]]:
    """
    Recursively scan for image files under data_dir.

    Returns a list of dicts with file metadata.
    """
    results: List[Dict[str, Any]] = []

    for filepath in sorted(data_dir.rglob("*")):
        if not filepath.is_file():
            continue
        if filepath.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        # Determine class from parent folder name
        original_class = filepath.parent.name

        # Determine split from grandparent (if applicable)
        relative = filepath.relative_to(data_dir)
        parts = relative.parts
        source_split = parts[0] if len(parts) >= 3 else "unknown"

        record: Dict[str, Any] = {
            "filename": filepath.name,
            "original_class": original_class,
            "relative_path": str(relative),
            "absolute_path": str(filepath.resolve()),
            "file_size": filepath.stat().st_size,
            "source_split": source_split,
        }

        # Validate image
        is_valid, size = validate_image(filepath)
        record["is_valid"] = is_valid
        if size:
            record["width"], record["height"] = size
        else:
            record["width"], record["height"] = None, None

        # Compute hash
        try:
            record["sha256"] = compute_sha256(filepath)
        except OSError:
            record["sha256"] = None
            record["is_valid"] = False

        results.append(record)

    return results


def find_duplicates(records: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Group records by SHA-256 and return groups with more than one file."""
    hash_groups: Dict[str, List[str]] = defaultdict(list)
    for rec in records:
        sha = rec.get("sha256")
        if sha:
            hash_groups[sha].append(rec["relative_path"])
    return {k: v for k, v in hash_groups.items() if len(v) > 1}


def audit(
    data_dir: Path,
    mapping_path: Path,
    min_samples: int = 20,
) -> Dict[str, Any]:
    """
    Run full audit on the raw dataset.

    Returns a dict with all audit findings.
    """
    print(f"[audit] Scanning images in {data_dir} ...")
    records = scan_images(data_dir)
    print(f"[audit] Found {len(records)} image files.")

    # Load mapping
    class_mapping = load_class_mapping(mapping_path)
    mapped_originals: Set[str] = set(class_mapping.keys())

    # Per-class stats
    class_counts: Counter = Counter()
    invalid_images: List[Dict[str, Any]] = []
    all_originals: Set[str] = set()

    for rec in records:
        oc = rec["original_class"]
        all_originals.add(oc)
        class_counts[oc] += 1
        if not rec["is_valid"]:
            invalid_images.append(
                {"relative_path": rec["relative_path"], "original_class": oc}
            )

    # Classes not in mapping
    unmapped_classes = sorted(all_originals - mapped_originals)

    # Classes in mapping but not found in data
    missing_classes = sorted(mapped_originals - all_originals)

    # Classes with too few samples
    small_classes = {
        cls: count for cls, count in class_counts.items() if count < min_samples
    }

    # Target class distribution (after mapping)
    target_counts: Counter = Counter()
    for rec in records:
        target = class_mapping.get(rec["original_class"])
        if target:
            target_counts[target] += 1

    # Duplicates
    print("[audit] Computing SHA-256 duplicates ...")
    duplicates = find_duplicates(records)
    duplicate_count = sum(len(v) for v in duplicates.values())

    report: Dict[str, Any] = {
        "data_dir": str(data_dir.resolve()),
        "total_images": len(records),
        "valid_images": sum(1 for r in records if r["is_valid"]),
        "invalid_images_count": len(invalid_images),
        "invalid_images": invalid_images,
        "unique_original_classes": len(all_originals),
        "original_class_counts": dict(sorted(class_counts.items())),
        "mapped_target_classes": len(target_counts),
        "target_class_counts": dict(sorted(target_counts.items())),
        "unmapped_classes": unmapped_classes,
        "missing_from_data": missing_classes,
        "small_classes": dict(sorted(small_classes.items())),
        "min_samples_threshold": min_samples,
        "duplicate_groups": len(duplicates),
        "duplicate_file_count": duplicate_count,
        "duplicates": {k: v for k, v in list(duplicates.items())[:50]},  # cap for readability
    }
    return report


def save_report(report: Dict[str, Any], output_path: Path) -> None:
    """Save audit report as JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"[audit] JSON report saved to {output_path}")


def save_csv_summary(report: Dict[str, Any], output_path: Path) -> None:
    """Save a CSV summary of per-class counts."""
    csv_path = output_path.with_suffix(".csv")
    rows = []
    for cls, count in sorted(report["original_class_counts"].items()):
        rows.append({"original_class": cls, "count": count})

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["original_class", "count"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"[audit] CSV summary saved to {csv_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Fruits-360 raw dataset")
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Path to raw dataset directory",
    )
    parser.add_argument(
        "--mapping",
        type=Path,
        default=Path("configs/class_mapping.yaml"),
        help="Path to class_mapping.yaml",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/metadata/audit_report.json"),
        help="Output path for JSON report",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=20,
        help="Minimum samples per class to flag",
    )
    args = parser.parse_args()

    if not args.data_dir.exists():
        print(f"[ERROR] Data directory not found: {args.data_dir}", file=sys.stderr)
        sys.exit(1)

    if not args.mapping.exists():
        print(f"[ERROR] Mapping file not found: {args.mapping}", file=sys.stderr)
        sys.exit(1)

    report = audit(args.data_dir, args.mapping, args.min_samples)

    save_report(report, args.output)
    save_csv_summary(report, args.output)

    # Print summary
    print("\n" + "=" * 60)
    print("AUDIT SUMMARY")
    print("=" * 60)
    print(f"  Total images:          {report['total_images']}")
    print(f"  Valid images:          {report['valid_images']}")
    print(f"  Invalid images:        {report['invalid_images_count']}")
    print(f"  Original classes:      {report['unique_original_classes']}")
    print(f"  Mapped target classes: {report['mapped_target_classes']}")
    print(f"  Unmapped classes:      {len(report['unmapped_classes'])}")
    print(f"  Duplicate groups:      {report['duplicate_groups']}")
    print(f"  Small classes (<{report['min_samples_threshold']}):  {len(report['small_classes'])}")
    print("=" * 60)

    if report["unmapped_classes"]:
        print("\nUnmapped classes (not in class_mapping.yaml):")
        for cls in report["unmapped_classes"]:
            print(f"  - {cls}")

    if report["invalid_images_count"] > 0:
        print(f"\n{report['invalid_images_count']} invalid images found. See report for details.")


if __name__ == "__main__":
    main()
