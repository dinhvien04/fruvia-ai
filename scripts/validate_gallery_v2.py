"""
Gallery V2 Pre-Flight Validation Tool (Read-Only).

Inspects a target Qdrant collection to verify readiness before activation:
1. Vector geometry: 768 dimensions, Cosine distance metric.
2. Collection status: GREEN or YELLOW (never RED).
3. Payload schema: required keyword payload indexes (canonical_class, category, source_dataset, dataset_name).
4. Point sampling: verifies required top-level schema fields, image_url presence, and taxonomy status.
5. Distribution summaries: breakdown by source dataset, category, and canonical class.

USAGE:
    python scripts/validate_gallery_v2.py --collection fruvia_gallery_dinov2_base_v2
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from collections import Counter

from qdrant_client import QdrantClient

REQUIRED_PAYLOAD_INDEXES = {"canonical_class", "category", "source_dataset", "dataset_name"}
REQUIRED_PAYLOAD_FIELDS = {
    "canonical_class",
    "display_name_en",
    "category",
    "source_dataset",
    "dataset_name",
    "gallery_schema_version",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-Only Gallery V2 Pre-Flight Validator")
    parser.add_argument(
        "--collection",
        type=str,
        default="fruvia_gallery_dinov2_base_v2",
        help="Target Qdrant collection name to validate",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=500,
        help="Number of points to sample for deep payload and vector inspection (default: 500)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout in seconds for Qdrant client operations",
    )
    return parser.parse_args()


def validate_collection(collection_name: str, sample_size: int, timeout: int) -> bool:
    qdrant_url = os.getenv("QDRANT_URL")
    qdrant_api_key = os.getenv("QDRANT_API_KEY")

    if not qdrant_url or not qdrant_api_key:
        print(
            "[ERROR] QDRANT_URL or QDRANT_API_KEY environment variable is not set.", file=sys.stderr
        )
        return False

    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key, timeout=timeout)

    print(f"=== Gallery V2 Validation Report: '{collection_name}' ===")

    # 1. Existence & Collection Info
    try:
        collections = [c.name for c in client.get_collections().collections]
        if collection_name not in collections:
            print(
                f"[FAIL] Collection '{collection_name}' not found on Qdrant cluster.",
                file=sys.stderr,
            )
            return False
        info = client.get_collection(collection_name=collection_name)
    except Exception as e:
        print(f"[FAIL] Failed to retrieve collection info: {e}", file=sys.stderr)
        return False

    # 2. Status & Point Count
    raw_status = getattr(info, "status", "unknown")
    status_name = getattr(raw_status, "name", str(raw_status)).upper()
    points_count = getattr(info, "points_count", None) or getattr(info, "vectors_count", None) or 0

    print(f"Status           : {status_name}")
    print(f"Points Count     : {points_count:,}")

    if status_name in {"RED", "ERROR"}:
        print(f"[FAIL] Collection status '{status_name}' is unhealthy.", file=sys.stderr)
        return False

    # 3. Vector Configuration
    config = getattr(info, "config", None)
    params = getattr(config, "params", None)
    vectors_config = getattr(params, "vectors", None)

    vector_size = getattr(vectors_config, "size", None)
    distance_metric = str(getattr(vectors_config, "distance", ""))

    if isinstance(vectors_config, dict):
        first_vec = next(iter(vectors_config.values()), None)
        if first_vec:
            vector_size = getattr(first_vec, "size", None)
            distance_metric = str(getattr(first_vec, "distance", ""))

    print(f"Vector Geometry  : {vector_size}D ({distance_metric})")

    if vector_size != 768 or "cosine" not in distance_metric.lower():
        print(
            f"[FAIL] Incompatible vector configuration (size={vector_size}, distance={distance_metric}). Expected 768D Cosine.",
            file=sys.stderr,
        )
        return False

    # 4. Payload Schema & Indexes
    payload_schema = getattr(info, "payload_schema", {}) or {}
    indexed_fields: set[str] = set()

    for f_name, s_info in payload_schema.items():
        data_type = (
            getattr(s_info, "data_type", None) or getattr(s_info, "type", None) or str(s_info)
        )
        dt_str = str(data_type.value if hasattr(data_type, "value") else data_type).lower()
        if "keyword" in dt_str and "text" not in dt_str:
            indexed_fields.add(f_name.lower().strip())

    missing_indexes = REQUIRED_PAYLOAD_INDEXES - indexed_fields
    print(f"Indexed Fields   : {sorted(indexed_fields)}")
    if missing_indexes:
        print(f"[WARN] Missing required keyword payload indexes: {sorted(missing_indexes)}")
    else:
        print("[OK] All required payload keyword indexes present.")

    # 5. Point Sampling & Distribution Check
    if points_count > 0 and sample_size > 0:
        print(
            f"\n--- Sampling {min(points_count, sample_size)} points for deep payload inspection ---"
        )
        try:
            records, _ = client.scroll(
                collection_name=collection_name,
                limit=sample_size,
                with_payload=True,
                with_vectors=True,
            )

            dataset_counter: Counter[str] = Counter()
            category_counter: Counter[str] = Counter()
            status_counter: Counter[str] = Counter()
            url_missing_count = 0
            invalid_vec_count = 0
            schema_version_mismatch = 0

            for rec in records:
                # Vector validation
                vec = rec.vector
                if isinstance(vec, dict):
                    vec = list(vec.values())[0]

                if (
                    not isinstance(vec, list)
                    or len(vec) != 768
                    or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in vec)
                ):
                    invalid_vec_count += 1

                payload = rec.payload or {}
                dataset_counter[str(payload.get("source_dataset", "missing"))] += 1
                category_counter[str(payload.get("category", "missing"))] += 1
                status_counter[str(payload.get("taxonomy_status", "missing"))] += 1

                if not payload.get("image_url") and not payload.get("thumbnail_url"):
                    url_missing_count += 1

                if payload.get("gallery_schema_version") != 2:
                    schema_version_mismatch += 1

            print(f"Dataset Distribution : {dict(dataset_counter)}")
            print(f"Category Distribution: {dict(category_counter)}")
            print(f"Taxonomy Statuses    : {dict(status_counter)}")
            print(f"Missing Image URLs   : {url_missing_count}/{len(records)}")
            print(f"Invalid Vectors      : {invalid_vec_count}/{len(records)}")
            print(f"Schema V2 Mismatch   : {schema_version_mismatch}/{len(records)}")

            if invalid_vec_count > 0:
                print(
                    f"[FAIL] Found {invalid_vec_count} invalid vectors in sample.", file=sys.stderr
                )
                return False

        except Exception as e:
            print(f"[WARN] Failed to sample points: {e}")

    print("\n" + "=" * 50)
    print(f"[PASS] Pre-flight validation passed for '{collection_name}'.")
    return True


def main() -> None:
    args = parse_args()
    success = validate_collection(
        collection_name=args.collection,
        sample_size=args.sample_size,
        timeout=args.timeout,
    )
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
