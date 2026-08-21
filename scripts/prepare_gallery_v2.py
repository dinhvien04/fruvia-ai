"""
Unified Gallery V2 Migration Tool.

Migrates, standardizes, and normalizes vector points from source collections
(e.g., fruvia_fruits360_original_dinov2_base_v1 or packeat) into the unified
canonical collection: fruvia_gallery_dinov2_base_v2.

Features:
- Deterministic UUIDv5 based on composite key (source_collection + source_point_id) to eliminate collisions.
- Vector integrity verification (768 dimensions, Cosine distance).
- Atomic, typed checkpoint serialization (handles int/str/UUID offsets).
- Full metadata payload preservation.
- Full --dry-run mode support.
- Taxonomy-driven normalization (canonical_class, name_en, name_vi, category).

USAGE (DRY RUN):
    python scripts/prepare_gallery_v2.py \\
        --source-collection fruvia_fruits360_original_dinov2_base_v1 \\
        --target-collection fruvia_gallery_dinov2_base_v2 \\
        --batch-size 100 \\
        --limit 10 \\
        --dry-run
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.utils.taxonomy import get_taxonomy_manager

# Fruvia Gallery Migration Namespace for RFC 4122 UUIDv5 generation
FRUVIA_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "fruvia.ai.migration.gallery_v2")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unified Gallery V2 Point Migration Tool")
    parser.add_argument(
        "--source-collection",
        type=str,
        default="fruvia_fruits360_original_dinov2_base_v1",
        help="Source Qdrant collection name",
    )
    parser.add_argument(
        "--target-collection",
        type=str,
        default="fruvia_gallery_dinov2_base_v2",
        help="Target unified Qdrant collection name",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of vector points to process per batch (default: 100)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max points to process (optional cap for testing)",
    )
    parser.add_argument(
        "--checkpoint-file",
        type=Path,
        default=None,
        help="Path to resume checkpoint file (defaults to data/migrations/<source>__to__<target>.checkpoint.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Perform a dry-run without writing to Qdrant",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Timeout in seconds for Qdrant operations",
    )
    return parser.parse_args()


def get_default_checkpoint_path(source_collection: str, target_collection: str) -> Path:
    safe_source = source_collection.replace("/", "_").replace("\\", "_")
    safe_target = target_collection.replace("/", "_").replace("\\", "_")
    return Path(f"data/migrations/{safe_source}__to__{safe_target}.checkpoint.json")


def load_checkpoint(checkpoint_file: Path) -> dict[str, Any]:
    if checkpoint_file.exists():
        try:
            with open(checkpoint_file, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            print(f"[WARN] Could not parse existing checkpoint file ({e}). Starting fresh.")
    return {
        "last_point_id": None,
        "last_point_id_type": None,
        "total_migrated": 0,
        "batches_completed": 0,
        "updated_at": None,
    }


def save_checkpoint_atomic(checkpoint_file: Path, checkpoint: dict[str, Any]) -> None:
    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = checkpoint_file.with_suffix(".tmp")
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        temp_file.replace(checkpoint_file)
    except Exception as e:
        print(f"[WARN] Failed to atomically save checkpoint: {e}", file=sys.stderr)
        if temp_file.exists():
            with contextlib.suppress(OSError):
                temp_file.unlink()


def generate_deterministic_point_uuid(source_collection: str, source_point_id: int | str) -> str:
    """
    Generate deterministic RFC 4122 UUIDv5 to eliminate point ID collisions
    across multiple source collections and datasets.
    """
    composite_key = f"{source_collection}:{source_point_id}"
    return str(uuid.uuid5(FRUVIA_NAMESPACE, composite_key))


def normalize_point_payload(
    original_payload: dict[str, Any],
    tax_manager: Any,
    default_source_dataset: str = "fruits360",
) -> dict[str, Any]:
    """
    Transform raw point payload into standardized Gallery V2 schema while
    preserving custom source metadata and attributes.
    """
    raw_class = (
        original_payload.get("original_class")
        or original_payload.get("class_name")
        or original_payload.get("fruit_name")
        or original_payload.get("label")
        or "unknown"
    )
    payload_canonical = original_payload.get("canonical_class")
    payload_display = original_payload.get("display_name_en") or original_payload.get("name_en")

    canonical_class, name_en, name_vi, category = tax_manager.resolve(
        original_class=str(raw_class),
        payload_canonical=payload_canonical,
        payload_display=payload_display,
    )

    source_dataset = (
        original_payload.get("source_dataset")
        or original_payload.get("dataset_name")
        or default_source_dataset
    )
    dataset_name = original_payload.get("dataset_name") or source_dataset

    image_url = (
        original_payload.get("image_url")
        or original_payload.get("thumbnail_url")
        or original_payload.get("r2_url")
    )
    thumbnail_url = (
        original_payload.get("thumbnail_url") or original_payload.get("image_url") or image_url
    )

    # Preserve all existing attributes or initialize dictionary
    attributes = dict(original_payload.get("attributes", {}))
    for key, val in original_payload.items():
        if key not in {
            "canonical_class",
            "display_name",
            "display_name_en",
            "display_name_vi",
            "name_en",
            "name_vi",
            "category",
            "source_dataset",
            "dataset_name",
            "dataset_version",
            "image_url",
            "thumbnail_url",
            "original_class",
            "class_name",
            "fruit_name",
            "label",
            "attributes",
        }:
            attributes[key] = val

    return {
        "canonical_class": canonical_class,
        "display_name_en": name_en,
        "display_name_vi": name_vi,
        "category": category,
        "source_dataset": str(source_dataset),
        "dataset_name": str(dataset_name),
        "dataset_version": str(original_payload.get("dataset_version", "1")),
        "image_url": image_url,
        "thumbnail_url": thumbnail_url,
        "original_class": str(raw_class),
        "attributes": attributes,
    }


def main() -> None:
    args = parse_args()

    qdrant_url = os.getenv("QDRANT_URL")
    qdrant_api_key = os.getenv("QDRANT_API_KEY")

    if not qdrant_url or not qdrant_api_key:
        print(
            "[ERROR] QDRANT_URL or QDRANT_API_KEY environment variable is not set.", file=sys.stderr
        )
        sys.exit(1)

    checkpoint_file = (
        args.checkpoint_file
        if args.checkpoint_file is not None
        else get_default_checkpoint_path(args.source_collection, args.target_collection)
    )

    print("=== Fruvia Unified Gallery V2 Migration Tool ===")
    print(f"Source Collection : {args.source_collection}")
    print(f"Target Collection : {args.target_collection}")
    print(f"Batch Size        : {args.batch_size}")
    print(f"Dry Run Mode      : {args.dry_run}")
    print(f"Checkpoint File   : {checkpoint_file}")
    if args.limit:
        print(f"Point Limit Cap   : {args.limit}")
    print("-" * 50)

    try:
        client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key, timeout=args.timeout)
        tax_mgr = get_taxonomy_manager()

        # Check source collection exists
        collections = [c.name for c in client.get_collections().collections]
        if args.source_collection not in collections:
            print(
                f"[ERROR] Source collection '{args.source_collection}' not found in Qdrant.",
                file=sys.stderr,
            )
            sys.exit(1)

        # Check / create target collection if applying
        if not args.dry_run:
            if args.target_collection not in collections:
                print(
                    f"[INFO] Creating target collection '{args.target_collection}' with 768D Cosine..."
                )
                client.create_collection(
                    collection_name=args.target_collection,
                    vectors_config=VectorParams(size=768, distance=Distance.COSINE),
                )
                print("[SUCCESS] Target collection created.")
        else:
            print(
                f"[DRY-RUN] Target collection check: '{args.target_collection}' (768D Cosine schema required)."
            )

        checkpoint = load_checkpoint(checkpoint_file)
        offset: int | str | None = checkpoint.get("last_point_id")
        offset_type = checkpoint.get("last_point_id_type")
        if offset is not None and offset_type == "int":
            with contextlib.suppress(ValueError, TypeError):
                offset = int(offset)

        total_migrated = int(checkpoint.get("total_migrated", 0))
        batches_completed = int(checkpoint.get("batches_completed", 0))

        print(
            f"[RESUME] Starting from offset: {offset} (Migrated so far: {total_migrated}, Batches: {batches_completed})"
        )

        processed_this_run = 0

        while True:
            scroll_limit = args.batch_size
            if args.limit and (processed_this_run + scroll_limit > args.limit):
                scroll_limit = args.limit - processed_this_run
                if scroll_limit <= 0:
                    break

            records, next_offset = client.scroll(
                collection_name=args.source_collection,
                limit=scroll_limit,
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )

            if not records:
                print("[INFO] Reached end of points in source collection.")
                break

            target_points: list[PointStruct] = []

            for rec in records:
                # Vector validation
                vec = rec.vector
                if isinstance(vec, dict):
                    vec = list(vec.values())[0]  # named vectors support

                if not vec or len(vec) != 768:
                    print(
                        f"[WARN] Skipping point {rec.id}: Invalid vector dim ({len(vec) if vec else 0})"
                    )
                    continue

                raw_payload = rec.payload or {}
                norm_payload = normalize_point_payload(raw_payload, tax_mgr)

                # Deterministic composite UUIDv5
                pt_uuid = generate_deterministic_point_uuid(args.source_collection, rec.id)

                point_struct = PointStruct(
                    id=pt_uuid,
                    vector=vec,
                    payload=norm_payload,
                )
                target_points.append(point_struct)

            if not args.dry_run and target_points:
                client.upsert(
                    collection_name=args.target_collection,
                    points=target_points,
                    wait=True,
                )
                total_migrated += len(target_points)
                batches_completed += 1

                # Determine typed offset for serialization
                offset_val_to_save: int | str | None = None
                offset_type_to_save: str | None = None
                if next_offset is not None:
                    if isinstance(next_offset, int):
                        offset_val_to_save = next_offset
                        offset_type_to_save = "int"
                    else:
                        offset_val_to_save = str(next_offset)
                        offset_type_to_save = "str"

                save_checkpoint_atomic(
                    checkpoint_file,
                    {
                        "source_collection": args.source_collection,
                        "target_collection": args.target_collection,
                        "last_point_id": offset_val_to_save,
                        "last_point_id_type": offset_type_to_save,
                        "total_migrated": total_migrated,
                        "batches_completed": batches_completed,
                        "updated_at": time.time(),
                    },
                )
                print(
                    f"[UPSERTED] Batch of {len(target_points)} points. Total migrated: {total_migrated}"
                )
            else:
                total_migrated += len(target_points)
                print(
                    f"[DRY-RUN] Would upsert batch of {len(target_points)} points into '{args.target_collection}'. Sample payload:"
                )
                if target_points:
                    print(json.dumps(target_points[0].payload, indent=2, ensure_ascii=False))

            processed_this_run += len(records)
            offset = next_offset

            if next_offset is None or (args.limit and processed_this_run >= args.limit):
                break

            time.sleep(0.05)  # Safe throttle

        print("-" * 50)
        print(
            f"[COMPLETE] Migration run finished. Processed this session: {processed_this_run}. Total count: {total_migrated}"
        )

    except Exception as e:
        print(f"[ERROR] Migration failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
