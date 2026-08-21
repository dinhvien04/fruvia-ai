"""
Script to safely create payload indexes on Qdrant collections.

Supports payload indexing for:
- canonical_class -> keyword
- category        -> keyword
- source_dataset  -> keyword
- dataset_name    -> keyword

Two-phase execution model:
PHASE 1 (Read-Only Preflight):
    Inspects all fields across target collection.
    Classifies every field as EXISTS, MISSING, or INCOMPATIBLE.
    If ANY field is INCOMPATIBLE, aborts immediately before performing ANY writes.
PHASE 2 (Execution):
    Only executes if Phase 1 discovered zero incompatibilities.
    Creates missing indexes.

USAGE (DRY RUN):
    python scripts/create_qdrant_payload_indexes.py --collection fruvia_fruits360_original_dinov2_base_v1 --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import PayloadSchemaType

INDEX_FIELDS: dict[str, PayloadSchemaType] = {
    "canonical_class": PayloadSchemaType.KEYWORD,
    "category": PayloadSchemaType.KEYWORD,
    "source_dataset": PayloadSchemaType.KEYWORD,
    "dataset_name": PayloadSchemaType.KEYWORD,
}


def is_keyword_index_type(schema_info: Any) -> bool:
    """
    Check if schema_info represents an exact keyword payload index in Qdrant.
    Rejects text, integer, float, geo, bool, or None schemas.
    """
    if schema_info is None:
        return False
    data_type = (
        getattr(schema_info, "data_type", None) or getattr(schema_info, "type", None) or schema_info
    )
    if hasattr(data_type, "value"):
        data_type = data_type.value
    dt_str = str(data_type).lower().strip()
    return dt_str in {"keyword", "payloadschematype.keyword"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely create payload indexes on a target Qdrant collection."
    )
    parser.add_argument(
        "--collection",
        type=str,
        required=True,
        help="Target Qdrant collection name (e.g. fruvia_gallery_dinov2_base_v2)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Perform a dry-run without modifying Qdrant collection",
    )
    parser.add_argument(
        "--allow-runtime-key-for-local-migration",
        action="store_true",
        default=False,
        help="Explicitly permit using QDRANT_API_KEY if QDRANT_MIGRATION_API_KEY is not set (development/local only)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout in seconds for Qdrant client operations (default: 30)",
    )
    return parser.parse_args()


def inspect_collection_indexes(
    client: QdrantClient,
    collection_name: str,
) -> dict[str, tuple[str, str]]:
    """
    Phase 1: Read-only inspection of required fields on target collection.
    Returns mapping: field_name -> (status, details)
    Status values: 'EXISTS', 'MISSING', 'INCOMPATIBLE', 'ERROR'
    """
    collection_info = client.get_collection(collection_name=collection_name)
    existing_schema = getattr(collection_info, "payload_schema", {}) or {}

    results: dict[str, tuple[str, str]] = {}

    for field_name in INDEX_FIELDS:
        if field_name in existing_schema:
            schema_info = existing_schema[field_name]
            if is_keyword_index_type(schema_info):
                results[field_name] = ("EXISTS", "Keyword index already exists")
            else:
                data_type = (
                    getattr(schema_info, "data_type", None)
                    or getattr(schema_info, "type", None)
                    or str(schema_info)
                )
                results[field_name] = (
                    "INCOMPATIBLE",
                    f"Found incompatible schema type '{data_type}' (expected KEYWORD)",
                )
        else:
            results[field_name] = ("MISSING", "Field has no payload index")

    return results


def main() -> None:
    args = parse_args()

    qdrant_url = os.getenv("QDRANT_URL")
    migration_api_key = os.getenv("QDRANT_MIGRATION_API_KEY")
    runtime_api_key = os.getenv("QDRANT_API_KEY")

    if not qdrant_url:
        print("[ERROR] QDRANT_URL environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    api_key = migration_api_key
    if not api_key:
        if runtime_api_key and args.allow_runtime_key_for_local_migration:
            print(
                "[WARN] Using QDRANT_API_KEY for indexing because --allow-runtime-key-for-local-migration was provided.",
                file=sys.stderr,
            )
            api_key = runtime_api_key
        else:
            print(
                "[ERROR] QDRANT_MIGRATION_API_KEY is not set. Schema index creation requires an administrative migration key.\n"
                "Pass --allow-runtime-key-for-local-migration if running in local development.",
                file=sys.stderr,
            )
            sys.exit(1)

    print("=== Qdrant Payload Index Creator (Two-Phase Safety) ===")
    print(f"Target Collection : {args.collection}")
    print(f"Dry Run Mode      : {args.dry_run}")
    print(f"Required Fields   : {list(INDEX_FIELDS.keys())}")
    print("-" * 50)

    try:
        client = QdrantClient(url=qdrant_url, api_key=api_key, timeout=args.timeout)
        collections = client.get_collections()
        existing = [c.name for c in collections.collections]

        if args.collection not in existing:
            print(
                f"[ERROR] Target collection '{args.collection}' not found in Qdrant Cloud.",
                file=sys.stderr,
            )
            print(f"Available collections: {existing}", file=sys.stderr)
            sys.exit(1)

        print(f"[OK] Collection '{args.collection}' found on Qdrant cluster.")

        # --- PHASE 1: READ-ONLY PREFLIGHT ---
        print("\n--- Phase 1: Read-Only Schema Preflight ---")
        preflight_results = inspect_collection_indexes(client, args.collection)

        has_incompatible = False
        missing_fields: list[str] = []

        for field_name, (status, detail) in preflight_results.items():
            if status == "INCOMPATIBLE":
                print(f"  [INCOMPATIBLE] {field_name}: {detail}", file=sys.stderr)
                has_incompatible = True
            elif status == "EXISTS":
                print(f"  [EXISTS] {field_name}: {detail}")
            elif status == "MISSING":
                print(f"  [MISSING] {field_name}: {detail}")
                missing_fields.append(field_name)

        if has_incompatible:
            print(
                "\n[FAIL] Phase 1 failed: One or more fields have incompatible schemas. Performing ZERO writes.",
                file=sys.stderr,
            )
            sys.exit(1)

        print("[OK] Phase 1 passed: No schema incompatibilities found.")

        # --- PHASE 2: MUTATION (OR DRY RUN) ---
        print("\n--- Phase 2: Execution ---")
        if not missing_fields:
            print("[OK] All required payload indexes already exist. Nothing to create.")
            print("-" * 50)
            print("Payload indexing check completed successfully.")
            return

        for field_name in missing_fields:
            schema_type = INDEX_FIELDS[field_name]
            if args.dry_run:
                print(f"  [WOULD_CREATE] {field_name} -> KEYWORD")
            else:
                print(f"  [CREATING] {field_name} -> KEYWORD...")
                client.create_payload_index(
                    collection_name=args.collection,
                    field_name=field_name,
                    field_schema=schema_type,
                )
                print(f"  [CREATED] {field_name} -> KEYWORD")

        print("-" * 50)
        print("Payload indexing operation completed successfully.")

    except Exception as e:
        print(f"[ERROR] Failed to execute payload indexing: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
