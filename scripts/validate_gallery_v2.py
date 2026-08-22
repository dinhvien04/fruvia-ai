"""
Gallery V2 Pre-Flight Validation & Activation Gate Tool (Read-Only).

Inspects a target Qdrant collection to verify strict readiness before activation:
1. Vector geometry: exact 768 dimensions, Cosine distance metric.
2. Collection status: GREEN or YELLOW (fail on RED, GREY, ERROR, or unknown).
3. Payload schema: required keyword payload indexes (canonical_class, category, source_dataset, dataset_name).
4. Full payload scan: 100% coverage verification on mandatory fields without downloading vectors.
5. Vector sampling: verification of L2 norm, finite floats, and dimension on configurable sample.
6. URL coverage: verifies image_url / thumbnail_url meets required threshold (--min-image-url-coverage).
7. Taxonomy status: verifies zero unverified PackEat / unreviewed records unless explicitly permitted.
8. Optional expected total and per-source counts validation.

FAIL-CLOSED ACTIVATION GATE:
If any mandatory requirement fails, exits with non-zero exit code (1). Never prints [PASS] on warnings.

USAGE:
    python scripts/validate_gallery_v2.py \
        --collection fruvia_gallery_dinov2_base_v2 \
        --allowed-image-host <YOUR_ACTUAL_FRUVIA_PUBLIC_IMAGE_HOST> \
        --expect-total-count 431602
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from collections import Counter
from typing import Any
from urllib.parse import urlparse

from qdrant_client import QdrantClient

REQUIRED_PAYLOAD_INDEXES = {"canonical_class", "category", "source_dataset", "dataset_name"}
REQUIRED_PAYLOAD_FIELDS = {
    "canonical_class",
    "category",
    "source_dataset",
    "dataset_name",
    "source_collection",
    "source_point_id",
    "gallery_schema_version",
}


def is_keyword_index_type(schema_info: Any) -> bool:
    """Check if schema_info represents an exact keyword payload index in Qdrant."""
    if schema_info is None:
        return False
    data_type = (
        getattr(schema_info, "data_type", None) or getattr(schema_info, "type", None) or schema_info
    )
    if hasattr(data_type, "value"):
        data_type = data_type.value
    dt_str = str(data_type).lower().strip()
    return dt_str in {"keyword", "payloadschematype.keyword"}


UNVERIFIED_TAXONOMY_STATUSES = {
    "UNVERIFIED_PACKEAT",
    "UNVERIFIED",
    "MANUAL_REVIEW",
    "UNMATCHED",
    "PENDING_REVIEW",
    "UNMAPPED",
    "UNKNOWN",
}


def is_valid_http_url(url_str: str, allowed_hosts: list[str] | None = None) -> bool:
    """
    Validate if string is a valid HTTPS URL and matches allowed hostnames if specified.
    Requires HTTPS scheme, no embedded credentials, and exact hostname matching.
    """
    if not url_str or not isinstance(url_str, str):
        return False
    try:
        parsed = urlparse(url_str.strip())
        # Require HTTPS scheme strictly
        if parsed.scheme != "https" or not parsed.netloc:
            return False
        # Reject URLs with embedded credentials
        if parsed.username or parsed.password:
            return False
        # If allowed_hosts specified, enforce exact hostname match (case-insensitive)
        if allowed_hosts:
            host = (parsed.hostname or "").lower().strip()
            if not host:
                return False
            return host in {ah.lower().strip() for ah in allowed_hosts if ah}
        return True
    except Exception:
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-Only Gallery V2 Activation Gate & Pre-Flight Validator"
    )
    parser.add_argument(
        "--collection",
        type=str,
        default="fruvia_gallery_dinov2_base_v2",
        help="Target Qdrant collection name to validate",
    )
    parser.add_argument(
        "--vector-sample-size",
        type=int,
        default=500,
        help="Number of points to sample for vector numeric validation (default: 500)",
    )
    parser.add_argument(
        "--min-image-url-coverage",
        type=float,
        default=1.0,
        help="Minimum required ratio of points with valid image_url / thumbnail_url (default: 1.0 = 100%)",
    )
    parser.add_argument(
        "--allowed-image-host",
        action="append",
        type=str,
        default=[],
        help="Allowed host for image URLs (can be specified multiple times, e.g. --allowed-image-host pub-xxx.r2.dev)",
    )
    parser.add_argument(
        "--allow-unverified-taxonomy",
        action="store_true",
        default=False,
        help="Allow points with UNVERIFIED_PACKEAT or MANUAL_REVIEW taxonomy statuses",
    )
    parser.add_argument(
        "--expect-total-count",
        type=int,
        default=None,
        help="Optional exact total point count expected in the collection",
    )
    parser.add_argument(
        "--expect-source-count",
        action="append",
        type=str,
        default=[],
        help="Expected count for a specific source_dataset in format SOURCE=COUNT (can be repeated)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Timeout in seconds for Qdrant client operations",
    )
    return parser.parse_args()


def validate_gallery_v2_collection(
    collection_name: str,
    vector_sample_size: int = 500,
    min_image_url_coverage: float = 1.0,
    allowed_image_hosts: list[str] | None = None,
    allow_unverified_taxonomy: bool = False,
    expect_total_count: int | None = None,
    expect_source_counts: dict[str, int] | None = None,
    timeout: int = 60,
    client: QdrantClient | None = None,
) -> bool:
    """
    Perform rigorous read-only pre-flight validation on target collection.
    Returns True if collection strictly meets all Gallery V2 activation requirements, else False.
    """
    if client is None:
        qdrant_url = os.getenv("QDRANT_URL")
        qdrant_api_key = os.getenv("QDRANT_API_KEY")

        if not qdrant_url or not qdrant_api_key:
            print(
                "[FAIL] QDRANT_URL or QDRANT_API_KEY environment variable is not set.",
                file=sys.stderr,
            )
            return False

        client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key, timeout=timeout)

    print(f"=== Gallery V2 Activation Gate Inspection: '{collection_name}' ===")

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
    print(f"Reported Points  : {points_count:,}")

    if status_name not in {"GREEN", "YELLOW"}:
        print(
            f"[FAIL] Collection status '{status_name}' is unhealthy or not ready (must be GREEN or YELLOW).",
            file=sys.stderr,
        )
        return False

    # Image host allowlist validation
    if min_image_url_coverage > 0:
        cleaned_allowed_hosts = [h.strip() for h in (allowed_image_hosts or []) if h and h.strip()]
        if not cleaned_allowed_hosts:
            print(
                "[FAIL] Explicit non-empty --allowed-image-host must be provided for image URL validation.",
                file=sys.stderr,
            )
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

    # 4. Payload Schema & Indexes (Exact KEYWORD check)
    payload_schema = getattr(info, "payload_schema", {}) or {}
    indexed_fields: set[str] = set()

    for f_name, s_info in payload_schema.items():
        if is_keyword_index_type(s_info):
            indexed_fields.add(f_name.lower().strip())

    missing_indexes = REQUIRED_PAYLOAD_INDEXES - indexed_fields
    print(f"Keyword Indexes  : {sorted(indexed_fields)}")
    if missing_indexes:
        print(
            f"[FAIL] Missing required keyword payload indexes: {sorted(missing_indexes)}",
            file=sys.stderr,
        )
        return False
    print("[OK] All required payload keyword indexes present.")

    # 5. Full Payload Scan (with_vectors=False) for 100% Coverage Verification
    print("\n--- Performing Full Payload Scan (with_vectors=False) ---")
    field_present_counts: dict[str, int] = {f: 0 for f in REQUIRED_PAYLOAD_FIELDS}
    url_present_count = 0
    schema_v2_count = 0
    total_scanned_points = 0
    dataset_counter: Counter[str] = Counter()
    category_counter: Counter[str] = Counter()
    status_counter: Counter[str] = Counter()

    scroll_offset = None
    batch_size = 500

    try:
        while True:
            records, next_offset = client.scroll(
                collection_name=collection_name,
                limit=batch_size,
                offset=scroll_offset,
                with_payload=True,
                with_vectors=False,
            )
            if not records:
                break

            for rec in records:
                total_scanned_points += 1
                payload = rec.payload or {}

                # Check required fields
                for field in REQUIRED_PAYLOAD_FIELDS:
                    val = payload.get(field)
                    if val is not None and str(val).strip() != "" and str(val) != "unknown":
                        field_present_counts[field] += 1

                # URL presence and format validation
                img_url = payload.get("image_url") or payload.get("thumbnail_url")
                if is_valid_http_url(str(img_url), allowed_hosts=allowed_image_hosts):
                    url_present_count += 1

                # Schema version
                if payload.get("gallery_schema_version") == 2:
                    schema_v2_count += 1

                # Distributions
                dataset_counter[str(payload.get("source_dataset", "missing"))] += 1
                category_counter[str(payload.get("category", "missing"))] += 1
                raw_tax_status = payload.get("taxonomy_status", "missing")
                normalized_tax_status = (
                    str(raw_tax_status).strip().upper() if raw_tax_status is not None else "MISSING"
                )
                status_counter[normalized_tax_status] += 1

            scroll_offset = next_offset
            if next_offset is None:
                break

    except Exception as e:
        print(f"[FAIL] Full payload scan failed: {e}", file=sys.stderr)
        return False

    print(f"Total Points Scanned : {total_scanned_points:,}")
    if total_scanned_points == 0:
        print("[FAIL] Collection is empty (0 points).", file=sys.stderr)
        return False

    # Verify reported points vs scanned points (fail closed if mismatch)
    if points_count > 0 and points_count != total_scanned_points:
        print(
            f"[FAIL] Reported points_count ({points_count:,}) differs from actual scanned points ({total_scanned_points:,}).",
            file=sys.stderr,
        )
        return False

    # Check Total Count Expectation if provided
    if expect_total_count is not None and total_scanned_points != expect_total_count:
        print(
            f"[FAIL] Point count mismatch: found {total_scanned_points}, expected {expect_total_count}",
            file=sys.stderr,
        )
        return False

    # Check Source Distribution Expectations if provided
    if expect_source_counts:
        for src_name, exp_count in expect_source_counts.items():
            actual_count = dataset_counter.get(src_name, 0)
            if actual_count != exp_count:
                print(
                    f"[FAIL] Source '{src_name}' count mismatch: found {actual_count}, expected {exp_count}",
                    file=sys.stderr,
                )
                return False

    # Verify 100% Coverage on Mandatory Filter Fields
    mandatory_failed = False
    print("\n--- Field Coverage Analysis ---")
    for field in sorted(REQUIRED_PAYLOAD_FIELDS):
        count = field_present_counts[field]
        pct = (count / total_scanned_points) * 100.0
        print(f"  - {field:25s}: {count:,}/{total_scanned_points:,} ({pct:.2f}%)")
        if count != total_scanned_points:
            print(
                f"[FAIL] Field '{field}' does not have 100% coverage ({pct:.2f}%).", file=sys.stderr
            )
            mandatory_failed = True

    if mandatory_failed:
        return False

    # Schema V2 version check
    if schema_v2_count != total_scanned_points:
        print(
            f"[FAIL] Gallery schema version mismatch: {schema_v2_count}/{total_scanned_points} points have gallery_schema_version=2",
            file=sys.stderr,
        )
        return False

    # Image URL coverage
    url_pct = (url_present_count / total_scanned_points) if total_scanned_points > 0 else 0.0
    print(
        f"  - Image URL Coverage       : {url_present_count:,}/{total_scanned_points:,} ({url_pct * 100:.2f}%)"
    )
    if url_pct < min_image_url_coverage:
        print(
            f"[FAIL] Image URL coverage ({url_pct * 100:.2f}%) is below required threshold ({min_image_url_coverage * 100:.2f}%).",
            file=sys.stderr,
        )
        return False

    # Taxonomy Status Distribution & Gate
    print("\n--- Taxonomy Status Distribution ---")
    for st, cnt in sorted(status_counter.items()):
        pct = (cnt / total_scanned_points) * 100.0
        print(f"  - {st:25s}: {cnt:,} ({pct:.2f}%)")

    unverified_count = sum(
        cnt for st, cnt in status_counter.items() if st in UNVERIFIED_TAXONOMY_STATUSES
    )
    if unverified_count > 0 and not allow_unverified_taxonomy:
        print(
            f"[FAIL] Collection contains {unverified_count} unverified / unreviewed taxonomy records ({', '.join(sorted([st for st in status_counter if st in UNVERIFIED_TAXONOMY_STATUSES]))}). "
            "Pass --allow-unverified-taxonomy if intentional.",
            file=sys.stderr,
        )
        return False

    # 6. Vector Numeric Sampling
    if vector_sample_size > 0:
        sample_count = min(total_scanned_points, vector_sample_size)
        print(f"\n--- Sampling {sample_count} Points for Vector Numeric Inspection ---")
        try:
            sample_records, _ = client.scroll(
                collection_name=collection_name,
                limit=sample_count,
                with_payload=False,
                with_vectors=True,
            )
            if not sample_records:
                print("[FAIL] Failed to retrieve vector sample records.", file=sys.stderr)
                return False

            for rec in sample_records:
                vec = rec.vector
                if isinstance(vec, dict):
                    vec = list(vec.values())[0]

                if (
                    not isinstance(vec, list)
                    or len(vec) != 768
                    or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in vec)
                ):
                    print(
                        f"[FAIL] Point '{rec.id}' contains non-finite or invalid vector geometry.",
                        file=sys.stderr,
                    )
                    return False

                # L2 norm check
                l2_norm = math.sqrt(sum(x * x for x in vec))
                if abs(l2_norm - 1.0) > 0.05:
                    print(
                        f"[FAIL] Point '{rec.id}' vector is not L2 normalized (norm={l2_norm:.4f}).",
                        file=sys.stderr,
                    )
                    return False

            print(f"[OK] All {len(sample_records)} sampled vectors are finite 768D L2-normalized.")
        except Exception as e:
            print(f"[FAIL] Vector sampling inspection failed: {e}", file=sys.stderr)
            return False

    print("\n" + "=" * 60)
    print(f"[PASS] Pre-flight validation & activation gate passed for '{collection_name}'.")
    return True


def main() -> None:
    args = parse_args()

    # Parse expect-source-count arguments
    expect_source_counts: dict[str, int] = {}
    for item in args.expect_source_count:
        if "=" in item:
            src, cnt_str = item.split("=", 1)
            try:
                expect_source_counts[src.strip()] = int(cnt_str.strip())
            except ValueError:
                print(f"[ERROR] Invalid --expect-source-count format: '{item}'", file=sys.stderr)
                sys.exit(1)

    success = validate_gallery_v2_collection(
        collection_name=args.collection,
        vector_sample_size=args.vector_sample_size,
        min_image_url_coverage=args.min_image_url_coverage,
        allowed_image_hosts=args.allowed_image_host if args.allowed_image_host else None,
        allow_unverified_taxonomy=args.allow_unverified_taxonomy,
        expect_total_count=args.expect_total_count,
        expect_source_counts=expect_source_counts,
        timeout=args.timeout,
    )
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
