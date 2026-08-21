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
- Returns non-zero exit code (1) if any index has an incompatible data type schema.
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
        print(
            "[ERROR] QDRANT_URL or QDRANT_API_KEY environment variable is not set.", file=sys.stderr
        )
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
            print(
                f"[ERROR] Target collection '{args.collection}' not found in Qdrant Cloud.",
                file=sys.stderr,
            )
            print(f"Available collections: {existing}", file=sys.stderr)
            sys.exit(1)

        print(f"[OK] Collection '{args.collection}' found on Qdrant cluster.")

        collection_info = client.get_collection(collection_name=args.collection)
        existing_schema = getattr(collection_info, "payload_schema", {}) or {}

        has_incompatible = False

        for field_name, schema_type in INDEX_FIELDS.items():
            expected_type_str = str(
                schema_type.value if hasattr(schema_type, "value") else schema_type
            ).lower()

            if field_name in existing_schema:
                existing_info = existing_schema[field_name]
                data_type = (
                    getattr(existing_info, "data_type", None)
                    or getattr(existing_info, "type", None)
                    or str(existing_info)
                )
                data_type_str = str(
                    data_type.value if hasattr(data_type, "value") else data_type
                ).lower()

                if "keyword" in data_type_str and "text" not in data_type_str:
                    print(
                        f"[EXISTS] Payload index for field='{field_name}' already exists (type='{data_type_str}')."
                    )
                else:
                    print(
                        f"[INCOMPATIBLE] Payload index for field='{field_name}' exists with incompatible type '{data_type_str}' (expected '{expected_type_str}').",
                        file=sys.stderr,
                    )
                    has_incompatible = True
            else:
                if args.dry_run:
                    print(
                        f"[WOULD_CREATE] Payload index: field='{field_name}', type='{expected_type_str}'"
                    )
                else:
                    print(
                        f"[CREATE] Creating payload index: field='{field_name}', type='{expected_type_str}'..."
                    )
                    client.create_payload_index(
                        collection_name=args.collection,
                        field_name=field_name,
                        field_schema=schema_type,
                    )
                    print(f"[SUCCESS] Index created for '{field_name}'.")

        print("-" * 50)
        if has_incompatible:
            print(
                "[FAILED] One or more payload indexes have incompatible schemas.", file=sys.stderr
            )
            sys.exit(1)

        print("Payload indexing operation completed successfully.")

    except Exception as e:
        print(f"[ERROR] Failed to create payload indexes: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
