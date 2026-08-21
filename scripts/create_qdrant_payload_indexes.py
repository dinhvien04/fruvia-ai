"""
Script to safely create payload indexes on Qdrant collections.

Supports payload indexing for:
- canonical_class -> keyword
- category        -> keyword
- source_dataset  -> keyword
- dataset_name    -> keyword

USAGE (DRY RUN):
    python scripts/create_qdrant_payload_indexes.py --collection fruvia_fruits360_original_dinov2_base_v1 --dry-run

IMPORTANT:
- Requires QDRANT_URL and QDRANT_API_KEY environment variables.
- Never hardcodes credentials.
- Idempotent and safe.
- Default mode is informational / requires explicit collection name.
"""

from __future__ import annotations

import argparse
import os
import sys

from qdrant_client import QdrantClient
from qdrant_client.models import PayloadSchemaType

INDEX_FIELDS: dict[str, PayloadSchemaType] = {
    "canonical_class": PayloadSchemaType.KEYWORD,
    "category": PayloadSchemaType.KEYWORD,
    "source_dataset": PayloadSchemaType.KEYWORD,
    "dataset_name": PayloadSchemaType.KEYWORD,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create payload indexes on a target Qdrant collection."
    )
    parser.add_argument(
        "--collection",
        type=str,
        required=True,
        help="Target Qdrant collection name (e.g. fruvia_fruits360_original_dinov2_base_v1)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Perform a dry-run without modifying Qdrant collection",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout in seconds for Qdrant client operations (default: 30)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    qdrant_url = os.getenv("QDRANT_URL")
    qdrant_api_key = os.getenv("QDRANT_API_KEY")

    if not qdrant_url or not qdrant_api_key:
        print("[ERROR] QDRANT_URL or QDRANT_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    print("=== Qdrant Payload Index Creator ===")
    print(f"Target Collection : {args.collection}")
    print(f"Dry Run Mode      : {args.dry_run}")
    print(f"Indexed Fields    : {list(INDEX_FIELDS.keys())}")
    print("-" * 50)

    try:
        client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key, timeout=args.timeout)
        collections = client.get_collections()
        existing = [c.name for c in collections.collections]

        if args.collection not in existing:
            print(f"[ERROR] Target collection '{args.collection}' not found in Qdrant Cloud.", file=sys.stderr)
            print(f"Available collections: {existing}", file=sys.stderr)
            sys.exit(1)

        print(f"[OK] Collection '{args.collection}' found on Qdrant cluster.")

        for field_name, schema_type in INDEX_FIELDS.items():
            if args.dry_run:
                print(f"[DRY-RUN] Would create payload index: field='{field_name}', type='{schema_type}'")
            else:
                print(f"[APPLYING] Creating payload index: field='{field_name}', type='{schema_type}'...")
                client.create_payload_index(
                    collection_name=args.collection,
                    field_name=field_name,
                    field_schema=schema_type,
                )
                print(f"[SUCCESS] Index created for '{field_name}'.")

        print("-" * 50)
        print("Payload indexing operation completed.")

    except Exception as e:
        print(f"[ERROR] Failed to create payload indexes: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
