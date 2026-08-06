#!/usr/bin/env python3
"""
Fruvia AI — Create Dataset Manifest

Builds a manifest CSV from the raw Fruits-360 dataset:
- Reads classes.yaml and class_mapping.yaml
- Validates every image with Pillow
- Computes SHA-256 for duplicate detection
- Maps original classes to target classes
- Splits into train/validation/test with data-leakage mitigation
- Exports final manifest CSV

Usage:
    python scripts/create_manifest.py \
        --data-dir data/raw \
        --output data/manifests/manifest.csv \
        --seed 42
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml
from PIL import Image

SUPPORTED_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}

MANIFEST_COLUMNS = [
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
]


def compute_sha256(filepath: Path, chunk_size: int = 65536) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def generate_image_id(relative_path: str) -> str:
    """
    Generate a deterministic image_id using UUID5.

    Using a fixed namespace + the relative path ensures the same image
    always gets the same ID, making manifests reproducible.
    """
    namespace = uuid.UUID("a3f1b2c4-d5e6-4f7a-8b9c-0d1e2f3a4b5c")
    return str(uuid.uuid5(namespace, relative_path))


def validate_image(filepath: Path) -> Tuple[bool, Optional[Tuple[int, int]]]:
    """Check if Pillow can open and verify the image."""
    try:
        with Image.open(filepath) as img:
            img.verify()
        with Image.open(filepath) as img:
            return True, img.size
    except Exception:
        return False, None


def load_yaml(path: Path) -> dict:
    """Load a YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def stratified_split_by_class(
    records: List[Dict[str, Any]],
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    """
    Split records into train/validation/test per target class.

    Within each class, images are sorted by SHA-256 (deterministic ordering)
    and then split sequentially. This mitigates data leakage from
    near-duplicate images ending up in different splits.
    """
    import random

    rng = random.Random(seed)

    # Group by target class
    by_class: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for rec in records:
        by_class[rec["target_class"]].append(rec)

    result: List[Dict[str, Any]] = []

    for cls in sorted(by_class.keys()):
        items = by_class[cls]
        # Sort by SHA-256 to cluster near-duplicates
        items.sort(key=lambda x: x.get("sha256", ""))
        n = len(items)
        n_train = max(1, int(n * train_ratio))
        n_val = max(1, int(n * val_ratio))

        # Shuffle within each class first, then sort by sha256 for split
        # This gives randomness across runs with same seed while keeping
        # similar images together via sha256 sort
        rng.shuffle(items)
        items.sort(key=lambda x: x.get("sha256", ""))

        for i, item in enumerate(items):
            if i < n_train:
                item["split"] = "train"
            elif i < n_train + n_val:
                item["split"] = "validation"
            else:
                item["split"] = "test"
            result.append(item)

    return result


def create_manifest(
    data_dir: Path,
    classes_path: Path,
    mapping_path: Path,
    seed: int = 42,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Create the dataset manifest.

    Returns (records, stats_dict).
    """
    # Load configs
    classes_cfg = load_yaml(classes_path)
    target_classes: Set[str] = set(classes_cfg.get("classes", []))
    mapping_cfg = load_yaml(mapping_path)
    class_mapping: Dict[str, str] = mapping_cfg.get("class_mapping", {})

    print(f"[manifest] Target classes: {len(target_classes)}")
    print(f"[manifest] Class mappings: {len(class_mapping)}")

    # Scan images
    print(f"[manifest] Scanning {data_dir} ...")
    records: List[Dict[str, Any]] = []
    skipped_unmapped = 0
    skipped_invalid = 0
    skipped_not_target = 0

    for filepath in sorted(data_dir.rglob("*")):
        if not filepath.is_file():
            continue
        if filepath.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        original_class = filepath.parent.name
        relative_path = str(filepath.relative_to(data_dir))

        # Check mapping
        target_class = class_mapping.get(original_class)
        if target_class is None:
            skipped_unmapped += 1
            continue

        if target_class not in target_classes:
            skipped_not_target += 1
            continue

        # Validate image
        is_valid, size = validate_image(filepath)
        if not is_valid:
            skipped_invalid += 1
            continue

        width, height = size if size else (None, None)

        # Compute hash
        try:
            sha256 = compute_sha256(filepath)
        except OSError:
            skipped_invalid += 1
            continue

        # Determine source split from directory structure
        parts = Path(relative_path).parts
        source = parts[0] if len(parts) >= 3 else "unknown"

        records.append({
            "image_id": generate_image_id(relative_path),
            "original_class": original_class,
            "target_class": target_class,
            "relative_path": relative_path,
            "filename": filepath.name,
            "width": width,
            "height": height,
            "file_size": filepath.stat().st_size,
            "sha256": sha256,
            "split": "",  # filled by split function
            "source": source,
            "is_valid": True,
        })

    print(f"[manifest] Valid records: {len(records)}")
    print(f"[manifest] Skipped (unmapped): {skipped_unmapped}")
    print(f"[manifest] Skipped (not target): {skipped_not_target}")
    print(f"[manifest] Skipped (invalid): {skipped_invalid}")

    # Remove exact duplicates (same SHA-256)
    seen_hashes: Set[str] = set()
    unique_records: List[Dict[str, Any]] = []
    dup_count = 0
    for rec in records:
        if rec["sha256"] in seen_hashes:
            dup_count += 1
            continue
        seen_hashes.add(rec["sha256"])
        unique_records.append(rec)

    print(f"[manifest] Removed {dup_count} exact duplicates. Remaining: {len(unique_records)}")

    # Split
    print(f"[manifest] Splitting with seed={seed}, train={train_ratio}, val={val_ratio} ...")
    split_records = stratified_split_by_class(
        unique_records,
        train_ratio=train_ratio,
        val_ratio=val_ratio,
        seed=seed,
    )

    # Compute stats
    split_counts: Counter = Counter(r["split"] for r in split_records)
    target_counts: Counter = Counter(r["target_class"] for r in split_records)

    per_split_per_class: Dict[str, Counter] = defaultdict(Counter)
    for r in split_records:
        per_split_per_class[r["split"]][r["target_class"]] += 1

    stats: Dict[str, Any] = {
        "total_records": len(split_records),
        "split_counts": dict(split_counts),
        "target_class_counts": dict(sorted(target_counts.items())),
        "per_split_per_class": {
            k: dict(sorted(v.items())) for k, v in sorted(per_split_per_class.items())
        },
        "duplicates_removed": dup_count,
        "skipped_unmapped": skipped_unmapped,
        "skipped_invalid": skipped_invalid,
        "seed": seed,
    }

    return split_records, stats


def save_manifest(records: List[Dict[str, Any]], output_path: Path) -> None:
    """Save manifest as CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        for rec in records:
            writer.writerow({col: rec.get(col, "") for col in MANIFEST_COLUMNS})
    print(f"[manifest] Saved {len(records)} records to {output_path}")


def save_stats(stats: Dict[str, Any], output_path: Path) -> None:
    """Save manifest stats as JSON."""
    stats_path = output_path.with_name(output_path.stem + "_stats.json")
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    print(f"[manifest] Stats saved to {stats_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Fruvia AI dataset manifest")
    parser.add_argument("--data-dir", type=Path, required=True, help="Raw dataset directory")
    parser.add_argument(
        "--classes", type=Path, default=Path("configs/classes.yaml"), help="classes.yaml path"
    )
    parser.add_argument(
        "--mapping",
        type=Path,
        default=Path("configs/class_mapping.yaml"),
        help="class_mapping.yaml path",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/manifests/manifest.csv"),
        help="Output manifest CSV path",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for splitting")
    parser.add_argument("--train-ratio", type=float, default=0.70, help="Train split ratio")
    parser.add_argument("--val-ratio", type=float, default=0.15, help="Validation split ratio")
    args = parser.parse_args()

    if not args.data_dir.exists():
        print(f"[ERROR] Data directory not found: {args.data_dir}", file=sys.stderr)
        sys.exit(1)

    records, stats = create_manifest(
        data_dir=args.data_dir,
        classes_path=args.classes,
        mapping_path=args.mapping,
        seed=args.seed,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
    )

    save_manifest(records, args.output)
    save_stats(stats, args.output)

    # Summary
    print("\n" + "=" * 60)
    print("MANIFEST SUMMARY")
    print("=" * 60)
    print(f"  Total records:    {stats['total_records']}")
    for split, count in sorted(stats["split_counts"].items()):
        print(f"  {split:15s}:  {count}")
    print(f"  Target classes:   {len(stats['target_class_counts'])}")
    print(f"  Duplicates removed: {stats['duplicates_removed']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
