"""
Unified Gallery V2 Migration Tool.

Migrates, standardizes, and normalizes vector points from source collections
(e.g., fruvia_fruits360_original_dinov2_base_v1 or packeat) into the unified
canonical collection: fruvia_gallery_dinov2_base_v2.

Features:
- Deterministic UUIDv5 based on composite key (source_collection + source_point_id) to eliminate collisions.
- Pre-flight vector integrity and schema verification (768 dimensions, Cosine distance).
- Atomic, typed, versioned checkpoint serialization with source/target identity validation.
- Top-level Gallery V2 payload schema preserving provenance and attributes.
- Strict vector validation: fail-closed by default, durable JSONL skip reporting with --skip-invalid.
- Automatic payload keyword index creation on new target collection creation.
- Strict taxonomy resolution (allow_heuristic=False) with custom taxonomy mapping support.
- Full --dry-run mode support.

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
import math
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, PointStruct, VectorParams

from app.utils.taxonomy import get_taxonomy_manager

# Fruvia Gallery Migration Namespace for RFC 4122 UUIDv5 generation
FRUVIA_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "fruvia.ai.migration.gallery_v2")

REQUIRED_PAYLOAD_INDEXES: dict[str, PayloadSchemaType] = {
    "canonical_class": PayloadSchemaType.KEYWORD,
    "category": PayloadSchemaType.KEYWORD,
    "source_dataset": PayloadSchemaType.KEYWORD,
    "dataset_name": PayloadSchemaType.KEYWORD,
}


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
        "--source-dataset",
        type=str,
        default=None,
        help="Default source dataset identifier if missing from payload",
    )
    parser.add_argument(
        "--dataset-version",
        type=str,
        default="1",
        help="Default dataset version if missing from payload (default: 1)",
    )
    parser.add_argument(
        "--taxonomy-mapping",
        type=Path,
        default=None,
        help="Optional path to custom taxonomy mapping JSON (e.g. configs/packeat_mapping.json)",
    )
    parser.add_argument(
        "--skip-invalid",
        action="store_true",
        default=False,
        help="Log and skip invalid/non-finite vectors instead of aborting migration",
    )
    parser.add_argument(
        "--ignore-invalid-checkpoint",
        action="store_true",
        default=False,
        help="Discard corrupt or mismatched checkpoint and start fresh instead of raising error",
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


def get_default_skipped_path(source_collection: str, target_collection: str) -> Path:
    safe_source = source_collection.replace("/", "_").replace("\\", "_")
    safe_target = target_collection.replace("/", "_").replace("\\", "_")
    return Path(f"data/migrations/{safe_source}__to__{safe_target}.skipped.jsonl")


def load_checkpoint(
    checkpoint_file: Path,
    source_collection: str,
    target_collection: str,
    ignore_invalid: bool = False,
) -> dict[str, Any]:
    """
    Load and validate existing checkpoint file.
    Enforces checkpoint schema version 1, source/target collection identity,
    and fail-closed integrity checks.
    """
    if not checkpoint_file.exists():
        return {
            "version": 1,
            "source_collection": source_collection,
            "target_collection": target_collection,
            "next_offset": None,
            "next_offset_type": None,
            "total_processed": 0,
            "total_migrated": 0,
            "total_skipped": 0,
            "batches_completed": 0,
            "updated_at": None,
        }

    try:
        with open(checkpoint_file, encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("Checkpoint content is not a JSON object")

            # Validate collections match
            saved_source = data.get("source_collection")
            saved_target = data.get("target_collection")

            if saved_source and saved_source != source_collection:
                raise ValueError(
                    f"Checkpoint source_collection '{saved_source}' does not match requested '{source_collection}'"
                )
            if saved_target and saved_target != target_collection:
                raise ValueError(
                    f"Checkpoint target_collection '{saved_target}' does not match requested '{target_collection}'"
                )

            # Ensure required keys exist
            data.setdefault("version", 1)
            data["source_collection"] = source_collection
            data["target_collection"] = target_collection
            data.setdefault("next_offset", data.get("last_point_id"))
            data.setdefault("next_offset_type", data.get("last_point_id_type"))
            data.setdefault("total_processed", data.get("total_migrated", 0))
            data.setdefault("total_migrated", 0)
            data.setdefault("total_skipped", 0)
            data.setdefault("batches_completed", 0)
            return data

    except Exception as e:
        if ignore_invalid:
            print(
                f"[WARN] Checkpoint validation failed ({e}). --ignore-invalid-checkpoint is set; starting fresh."
            )
            return {
                "version": 1,
                "source_collection": source_collection,
                "target_collection": target_collection,
                "next_offset": None,
                "next_offset_type": None,
                "total_processed": 0,
                "total_migrated": 0,
                "total_skipped": 0,
                "batches_completed": 0,
                "updated_at": None,
            }
        raise RuntimeError(
            f"Checkpoint file '{checkpoint_file}' is invalid or mismatched: {e}. Pass --ignore-invalid-checkpoint to overwrite."
        ) from e


def save_checkpoint_atomic(checkpoint_file: Path, checkpoint: dict[str, Any]) -> None:
    """
    Durable atomic checkpoint write with sync to disk.
    Raises exception on failure to ensure undurable migrations do not continue silently.
    """
    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = checkpoint_file.with_suffix(".tmp")
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        temp_file.replace(checkpoint_file)
    except Exception as e:
        if temp_file.exists():
            with contextlib.suppress(OSError):
                temp_file.unlink()
        raise OSError(f"Failed to atomically persist checkpoint to '{checkpoint_file}': {e}") from e


def log_skipped_point(
    skipped_file: Path,
    point_id: Any,
    source_collection: str,
    reason: str,
    raw_payload: dict[str, Any] | None = None,
) -> None:
    """Append durable skipped point record to JSONL log."""
    skipped_file.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": time.time(),
        "source_collection": source_collection,
        "point_id": str(point_id),
        "reason": reason,
        "payload_snippet": raw_payload or {},
    }
    with open(skipped_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()


def generate_deterministic_point_uuid(source_collection: str, source_point_id: int | str) -> str:
    """
    Generate deterministic RFC 4122 UUIDv5 to eliminate point ID collisions
    across multiple source collections and datasets.
    """
    composite_key = f"{source_collection}:{source_point_id}"
    return str(uuid.uuid5(FRUVIA_NAMESPACE, composite_key))


def validate_source_and_target_schema(
    client: QdrantClient,
    source_collection: str,
    target_collection: str,
    dry_run: bool,
) -> None:
    """
    Validate vector dimension (768) and distance (Cosine) for source and target collections.
    Creates target collection and required payload keyword indexes if missing and not dry_run.
    """
    collections = [c.name for c in client.get_collections().collections]
    if source_collection not in collections:
        raise RuntimeError(
            f"Source collection '{source_collection}' does not exist on Qdrant cluster."
        )

    # Validate source schema
    source_info = client.get_collection(collection_name=source_collection)
    source_config = getattr(source_info, "config", None)
    source_params = getattr(source_config, "params", None)
    source_vec_config = getattr(source_params, "vectors", None)

    source_size = getattr(source_vec_config, "size", None)
    source_dist = str(getattr(source_vec_config, "distance", ""))

    if isinstance(source_vec_config, dict):
        first_v = next(iter(source_vec_config.values()), None)
        if first_v:
            source_size = getattr(first_v, "size", None)
            source_dist = str(getattr(first_v, "distance", ""))

    if source_size != 768 or "cosine" not in source_dist.lower():
        raise RuntimeError(
            f"Source collection '{source_collection}' has incompatible schema (size={source_size}, dist={source_dist}). Expected 768D Cosine."
        )

    print(f"[OK] Source collection '{source_collection}' validated (768D Cosine).")

    # Target collection handling
    if target_collection in collections:
        target_info = client.get_collection(collection_name=target_collection)
        target_config = getattr(target_info, "config", None)
        target_params = getattr(target_config, "params", None)
        target_vec_config = getattr(target_params, "vectors", None)

        target_size = getattr(target_vec_config, "size", None)
        target_dist = str(getattr(target_vec_config, "distance", ""))

        if isinstance(target_vec_config, dict):
            first_v = next(iter(target_vec_config.values()), None)
            if first_v:
                target_size = getattr(first_v, "size", None)
                target_dist = str(getattr(first_v, "distance", ""))

        if target_size != 768 or "cosine" not in target_dist.lower():
            raise RuntimeError(
                f"Target collection '{target_collection}' exists with incompatible schema (size={target_size}, dist={target_dist})."
            )
        print(f"[OK] Existing target collection '{target_collection}' validated (768D Cosine).")
    elif not dry_run:
        print(
            f"[INFO] Target collection '{target_collection}' does not exist. Creating 768D Cosine collection..."
        )
        client.create_collection(
            collection_name=target_collection,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )
        print(f"[SUCCESS] Target collection '{target_collection}' created.")

        # Create required payload keyword indexes immediately
        for field_name, schema_type in REQUIRED_PAYLOAD_INDEXES.items():
            print(f"[INDEX] Creating payload index on target: {field_name} (KEYWORD)...")
            client.create_payload_index(
                collection_name=target_collection,
                field_name=field_name,
                field_schema=schema_type,
            )
        print("[SUCCESS] All required payload indexes created on target collection.")
    else:
        print(
            f"[DRY-RUN] Target collection '{target_collection}' would be created with 768D Cosine and payload indexes."
        )


def normalize_point_payload(
    original_payload: dict[str, Any],
    tax_manager: Any,
    source_collection: str,
    source_point_id: Any,
    default_source_dataset: str | None = None,
    default_dataset_version: str = "1",
    custom_mapping: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Transform raw point payload into standardized Gallery V2 top-level schema
    preserving full provenance without fabricating missing metadata.
    """
    raw_class = (
        original_payload.get("original_class")
        or original_payload.get("class_name")
        or original_payload.get("fruit_name")
        or original_payload.get("label")
        or original_payload.get("class")
    )
    raw_class_str = str(raw_class).strip() if raw_class is not None else "unknown"

    payload_canonical = original_payload.get("canonical_class")
    payload_display = (
        original_payload.get("display_name")
        or original_payload.get("display_name_en")
        or original_payload.get("name_en")
    )

    # Check custom mapping first if provided
    mapped_canon = None
    if custom_mapping and raw_class_str in custom_mapping:
        mapped_canon = custom_mapping[raw_class_str]

    canonical_class, name_en, name_vi, category = tax_manager.resolve(
        original_class=raw_class_str,
        payload_canonical=mapped_canon or payload_canonical,
        payload_display=payload_display,
        allow_heuristic=False,  # Strict resolution for migrations
    )

    # Determine taxonomy status
    if payload_canonical or (custom_mapping and raw_class_str in custom_mapping):
        taxonomy_status = "CANONICAL"
    elif canonical_class == raw_class_str:
        taxonomy_status = "EXACT"
    elif canonical_class != "unknown" and canonical_class != raw_class_str:
        taxonomy_status = "ALIAS"
    else:
        taxonomy_status = "UNMAPPED"

    # Dataset resolution
    source_dataset = (
        original_payload.get("source_dataset")
        or default_source_dataset
        or original_payload.get("dataset_name")
    )
    if not source_dataset:
        # Infer default from collection name or path
        img_url = str(original_payload.get("image_url", ""))
        if "packeat" in source_collection.lower() or "packeat" in img_url:
            source_dataset = "packeat"
        elif "262" in source_collection.lower() or "262" in img_url:
            source_dataset = "fruits262"
        else:
            source_dataset = "fruits360"

    dataset_name = original_payload.get("dataset_name") or str(source_dataset)
    dataset_version = str(original_payload.get("dataset_version") or default_dataset_version)

    image_url = (
        original_payload.get("image_url")
        or original_payload.get("thumbnail_url")
        or original_payload.get("r2_url")
    )
    thumbnail_url = (
        original_payload.get("thumbnail_url") or original_payload.get("image_url") or image_url
    )

    filename = original_payload.get("filename")
    relative_path = original_payload.get("relative_path")
    original_split = original_payload.get("original_split") or original_payload.get("source")
    r2_key = original_payload.get("r2_key")

    # Collect custom attributes
    known_fields = {
        "canonical_class",
        "original_class",
        "display_name",
        "display_name_en",
        "display_name_vi",
        "name_en",
        "name_vi",
        "category",
        "source_dataset",
        "dataset_name",
        "dataset_version",
        "filename",
        "relative_path",
        "original_split",
        "source",
        "image_url",
        "thumbnail_url",
        "r2_url",
        "r2_key",
        "class_name",
        "fruit_name",
        "label",
        "class",
        "attributes",
        "embedding_model",
        "embedding_dimension",
        "embedding_pooling",
        "embedding_normalization",
        "taxonomy_status",
        "source_collection",
        "source_point_id",
        "gallery_schema_version",
    }

    attributes = dict(original_payload.get("attributes", {}))
    for key, val in original_payload.items():
        if key not in known_fields:
            attributes[key] = val

    return {
        "canonical_class": canonical_class,
        "original_class": raw_class_str,
        "display_name": name_en,
        "display_name_en": name_en,
        "display_name_vi": name_vi,
        "category": category,
        "source_dataset": str(source_dataset),
        "dataset_name": str(dataset_name),
        "dataset_version": dataset_version,
        "filename": str(filename) if filename is not None else None,
        "relative_path": str(relative_path) if relative_path is not None else None,
        "original_split": str(original_split) if original_split is not None else None,
        "image_url": str(image_url) if image_url is not None else None,
        "thumbnail_url": str(thumbnail_url) if thumbnail_url is not None else None,
        "r2_key": str(r2_key) if r2_key is not None else None,
        "embedding_model": "facebook/dinov2-base",
        "embedding_dimension": 768,
        "embedding_pooling": "cls",
        "embedding_normalization": "l2",
        "taxonomy_status": taxonomy_status,
        "source_collection": source_collection,
        "source_point_id": str(source_point_id),
        "gallery_schema_version": 2,
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
    skipped_file = get_default_skipped_path(args.source_collection, args.target_collection)

    print("=== Fruvia Unified Gallery V2 Migration Tool ===")
    print(f"Source Collection : {args.source_collection}")
    print(f"Target Collection : {args.target_collection}")
    print(f"Batch Size        : {args.batch_size}")
    print(f"Dry Run Mode      : {args.dry_run}")
    print(f"Skip Invalid      : {args.skip_invalid}")
    print(f"Checkpoint File   : {checkpoint_file}")
    if args.limit:
        print(f"Point Limit Cap   : {args.limit}")
    print("-" * 50)

    try:
        client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key, timeout=args.timeout)
        tax_mgr = get_taxonomy_manager()

        # Load custom mapping if provided
        custom_mapping: dict[str, str] | None = None
        if args.taxonomy_mapping and args.taxonomy_mapping.exists():
            with open(args.taxonomy_mapping, encoding="utf-8") as mf:
                custom_mapping = json.load(mf)
                print(
                    f"[OK] Loaded {len(custom_mapping)} custom taxonomy mappings from {args.taxonomy_mapping}"
                )

        # Pre-flight schema validation
        validate_source_and_target_schema(
            client=client,
            source_collection=args.source_collection,
            target_collection=args.target_collection,
            dry_run=args.dry_run,
        )

        checkpoint = load_checkpoint(
            checkpoint_file=checkpoint_file,
            source_collection=args.source_collection,
            target_collection=args.target_collection,
            ignore_invalid=args.ignore_invalid_checkpoint,
        )

        offset: int | str | None = checkpoint.get("next_offset")
        offset_type = checkpoint.get("next_offset_type")
        if offset is not None and offset_type == "int":
            with contextlib.suppress(ValueError, TypeError):
                offset = int(offset)

        total_processed = int(checkpoint.get("total_processed", 0))
        total_migrated = int(checkpoint.get("total_migrated", 0))
        total_skipped = int(checkpoint.get("total_skipped", 0))
        batches_completed = int(checkpoint.get("batches_completed", 0))

        print(
            f"[RESUME] Starting from offset: {offset} (Migrated: {total_migrated}, Skipped: {total_skipped}, Batches: {batches_completed})"
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
            skipped_this_batch = 0

            for rec in records:
                # Vector validation
                vec = rec.vector
                if isinstance(vec, dict):
                    vec = list(vec.values())[0]

                is_valid = (
                    isinstance(vec, list)
                    and len(vec) == 768
                    and all(isinstance(x, (int, float)) and math.isfinite(x) for x in vec)
                )

                if not is_valid:
                    reason = f"Invalid vector format/dimension ({len(vec) if isinstance(vec, list) else type(vec)})"
                    if not args.skip_invalid:
                        raise RuntimeError(
                            f"Point {rec.id} in collection '{args.source_collection}' has invalid vector: {reason}. Aborting migration. Pass --skip-invalid to log and continue."
                        )
                    print(f"[SKIP] Point {rec.id}: {reason}")
                    log_skipped_point(
                        skipped_file, rec.id, args.source_collection, reason, rec.payload
                    )
                    skipped_this_batch += 1
                    continue

                raw_payload = rec.payload or {}
                norm_payload = normalize_point_payload(
                    original_payload=raw_payload,
                    tax_manager=tax_mgr,
                    source_collection=args.source_collection,
                    source_point_id=rec.id,
                    default_source_dataset=args.source_dataset,
                    default_dataset_version=args.dataset_version,
                    custom_mapping=custom_mapping,
                )

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
                total_skipped += skipped_this_batch
                total_processed += len(records)
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
                        "version": 1,
                        "source_collection": args.source_collection,
                        "target_collection": args.target_collection,
                        "next_offset": offset_val_to_save,
                        "next_offset_type": offset_type_to_save,
                        "total_processed": total_processed,
                        "total_migrated": total_migrated,
                        "total_skipped": total_skipped,
                        "batches_completed": batches_completed,
                        "updated_at": time.time(),
                    },
                )
                print(
                    f"[UPSERTED] Batch of {len(target_points)} points. Total migrated: {total_migrated}, Skipped: {total_skipped}"
                )
            else:
                total_migrated += len(target_points)
                total_skipped += skipped_this_batch
                total_processed += len(records)
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
            f"[COMPLETE] Migration run finished. Processed this run: {processed_this_run}. Total migrated: {total_migrated}, Total skipped: {total_skipped}"
        )

    except Exception as e:
        print(f"[ERROR] Migration failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
