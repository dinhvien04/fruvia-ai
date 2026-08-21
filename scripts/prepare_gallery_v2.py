"""
Unified Gallery V2 Migration Tool.

Migrates, standardizes, and normalizes vector points from source collections
(e.g., fruvia_fruits360_original_dinov2_base_v1 or packeat) into the unified
canonical collection: fruvia_gallery_dinov2_base_v2.

Features:
- Deterministic UUIDs and normalized payload schema.
- Vector integrity verification (768 dimensions, Cosine distance).
- Resumable migrations with checkpoint tracking.
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
import json
import os
import sys
import time
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.utils.taxonomy import get_taxonomy_manager


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
        default=Path("data/migration_checkpoint.json"),
        help="Path to resume checkpoint file",
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


def load_checkpoint(checkpoint_file: Path) -> dict[str, str | int]:
    if checkpoint_file.exists():
        try:
            with open(checkpoint_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_point_id": "", "total_migrated": 0}


def save_checkpoint(checkpoint_file: Path, checkpoint: dict[str, str | int]) -> None:
    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    with open(checkpoint_file, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2)


def normalize_point_payload(
    original_payload: dict,
    tax_manager,
    default_source_dataset: str = "fruits360",
) -> dict:
    """
    Transform raw point payload into standard Normalized Payload Schema.
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
        original_class=raw_class,
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
        original_payload.get("thumbnail_url")
        or original_payload.get("image_url")
        or image_url
    )

    return {
        "canonical_class": canonical_class,
        "display_name_en": name_en,
        "display_name_vi": name_vi,
        "category": category,
        "source_dataset": source_dataset,
        "dataset_name": dataset_name,
        "image_url": image_url,
        "thumbnail_url": thumbnail_url,
        "original_class": raw_class,
        "attributes": original_payload.get("attributes", {}),
    }


def main() -> None:
    args = parse_args()

    qdrant_url = os.getenv("QDRANT_URL")
    qdrant_api_key = os.getenv("QDRANT_API_KEY")

    if not qdrant_url or not qdrant_api_key:
        print("[ERROR] QDRANT_URL or QDRANT_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    print("=== Fruvia Unified Gallery V2 Migration Tool ===")
    print(f"Source Collection : {args.source_collection}")
    print(f"Target Collection : {args.target_collection}")
    print(f"Batch Size        : {args.batch_size}")
    print(f"Dry Run Mode      : {args.dry_run}")
    print(f"Checkpoint File   : {args.checkpoint_file}")
    if args.limit:
        print(f"Point Limit Cap   : {args.limit}")
    print("-" * 50)

    try:
        client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key, timeout=args.timeout)
        tax_mgr = get_taxonomy_manager()

        # Check source collection exists
        collections = [c.name for c in client.get_collections().collections]
        if args.source_collection not in collections:
            print(f"[ERROR] Source collection '{args.source_collection}' not found in Qdrant.", file=sys.stderr)
            sys.exit(1)

        # Check / create target collection if applying
        if not args.dry_run:
            if args.target_collection not in collections:
                print(f"[INFO] Creating target collection '{args.target_collection}' with 768D Cosine...")
                client.create_collection(
                    collection_name=args.target_collection,
                    vectors_config=VectorParams(size=768, distance=Distance.COSINE),
                )
                print("[SUCCESS] Target collection created.")
        else:
            print(f"[DRY-RUN] Would ensure target collection '{args.target_collection}' exists (768D Cosine).")

        checkpoint = load_checkpoint(args.checkpoint_file)
        offset = checkpoint.get("last_point_id") or None
        total_migrated = int(checkpoint.get("total_migrated", 0))

        print(f"[RESUME] Starting from offset point_id: {offset} (Previously migrated: {total_migrated})")

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
                print("[INFO] No more points to scroll from source collection.")
                break

            target_points: list[PointStruct] = []

            for rec in records:
                # Vector validation
                vec = rec.vector
                if isinstance(vec, dict):
                    vec = list(vec.values())[0]  # named vectors support

                if not vec or len(vec) != 768:
                    print(f"[WARN] Skipping point {rec.id}: Invalid vector dim ({len(vec) if vec else 0})")
                    continue

                raw_payload = rec.payload or {}
                norm_payload = normalize_point_payload(raw_payload, tax_mgr)

                # Consistent or generated UUID
                pt_id = rec.id
                if isinstance(pt_id, str):
                    try:
                        pt_uuid = str(uuid.UUID(pt_id))
                    except ValueError:
                        pt_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"fruvia_point_{pt_id}"))
                else:
                    pt_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"fruvia_point_{pt_id}"))

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
                save_checkpoint(
                    args.checkpoint_file,
                    {"last_point_id": str(next_offset) if next_offset else "", "total_migrated": total_migrated},
                )
                print(f"[UPSERTED] Batch of {len(target_points)} points. Total: {total_migrated}")
            else:
                total_migrated += len(target_points)
                print(f"[DRY-RUN] Would upsert batch of {len(target_points)} points into '{args.target_collection}'. Sample payload:")
                if target_points:
                    print(json.dumps(target_points[0].payload, indent=2, ensure_ascii=False))

            processed_this_run += len(records)
            offset = next_offset

            if next_offset is None or (args.limit and processed_this_run >= args.limit):
                break

            time.sleep(0.05)  # Safe throttle

        print("-" * 50)
        print(f"[COMPLETE] Migration run finished. Processed: {processed_this_run} points. Total count: {total_migrated}")

    except Exception as e:
        print(f"[ERROR] Migration failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
