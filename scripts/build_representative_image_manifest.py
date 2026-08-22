"""
Build deterministic representative image manifest for Fruvia Explore.

Scans the active Qdrant Gallery collection (payload-only, with_vectors=False) until offset
is exhausted or all taxonomy species have valid representative images.
Resolves true canonical classes via TaxonomyManager, applies strict URL security validation,
and outputs a deterministic, schema-versioned configs/representative_images.json file.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

# Add backend directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.repositories.qdrant_repository import get_qdrant_repository  # noqa: E402
from app.services.representative_image_service import is_safe_image_url  # noqa: E402
from app.utils.taxonomy import get_taxonomy_manager  # noqa: E402

MANIFEST_PATH = BASE_DIR / "configs" / "representative_images.json"
SCHEMA_VERSION = 1


def build_manifest(
    batch_size: int = 2000,
    output_path: Path = MANIFEST_PATH,
    early_exit_if_all_found: bool = True,
) -> dict[str, Any]:
    """
    Build deterministic representative images manifest by scanning active Qdrant Gallery.

    Deterministic Selection Policy:
    1. Only consider valid allowed HTTP/HTTPS URLs (according to production allowed host rules).
    2. Prefer points where payload canonical_class directly matches target canonical_class.
    3. Otherwise accept points where TaxonomyManager resolved original_class / aliases to the target.
    4. Tie-breaking: Stable lexicographically smallest point_id or first discovered candidate.
    """
    settings = get_settings()
    repo = get_qdrant_repository()
    taxonomy = get_taxonomy_manager()
    taxonomy.load()

    client = repo.client
    col_name = repo.collection_name
    allowed_hosts = settings.allowed_image_host_list or None
    is_prod = settings.is_production

    print(f"Building Representative Image Manifest for collection: '{col_name}'")
    print(f"Target Output: {output_path}")

    all_taxonomy_keys = sorted(list(taxonomy.taxonomy.keys()))
    print(f"Total Taxonomy Species: {len(all_taxonomy_keys)}")

    # Track chosen candidates per canonical class
    # Format: canonical_class -> {
    #   "image_url": str,
    #   "original_class": str,
    #   "source_dataset": str,
    #   "point_id": str,
    #   "is_exact_canonical": bool
    # }
    candidates: dict[str, dict[str, Any]] = {}
    remaining_species = set(all_taxonomy_keys)

    offset = None
    total_scanned = 0
    batch_idx = 0
    start_time = time.time()

    payload_fields = [
        "canonical_class",
        "original_class",
        "display_name",
        "image_url",
        "source_dataset",
        "dataset_name",
    ]

    while True:
        pts, offset = client.scroll(
            collection_name=col_name,
            limit=batch_size,
            offset=offset,
            with_payload=payload_fields,
            with_vectors=False,
        )
        if not pts:
            break

        total_scanned += len(pts)
        batch_idx += 1

        for p in pts:
            pl = p.payload or {}
            raw_url = pl.get("image_url")
            if not raw_url or not is_safe_image_url(
                raw_url, allowed_hosts=allowed_hosts, is_production=is_prod
            ):
                continue

            orig = pl.get("original_class") or ""
            raw_c = pl.get("canonical_class")
            disp = pl.get("display_name")
            source_ds = pl.get("source_dataset") or pl.get("dataset_name") or "unknown"
            pt_id = str(p.id)

            c_cls, _, _, _ = taxonomy.resolve(
                original_class=orig,
                payload_canonical=raw_c,
                payload_display=disp,
            )

            if not c_cls or c_cls not in taxonomy.taxonomy:
                continue

            is_exact = bool(raw_c and str(raw_c).strip().lower() == c_cls)

            existing = candidates.get(c_cls)
            if existing is None:
                candidates[c_cls] = {
                    "image_url": raw_url,
                    "original_class": orig,
                    "source_dataset": source_ds,
                    "point_id": pt_id,
                    "is_exact_canonical": is_exact,
                }
                if c_cls in remaining_species and is_exact:
                    remaining_species.remove(c_cls)
            elif not existing["is_exact_canonical"] and is_exact:
                # Upgrade to exact canonical payload match
                candidates[c_cls] = {
                    "image_url": raw_url,
                    "original_class": orig,
                    "source_dataset": source_ds,
                    "point_id": pt_id,
                    "is_exact_canonical": True,
                }
                if c_cls in remaining_species:
                    remaining_species.remove(c_cls)

        if early_exit_if_all_found and len(remaining_species) == 0:
            print(
                f"All {len(all_taxonomy_keys)} species resolved! Early exiting at batch {batch_idx}."
            )
            break

        if not offset:
            break

    elapsed = time.time() - start_time
    print(f"Scanned {total_scanned:,} points in {batch_idx} batches ({elapsed:.2f}s).")
    print(
        f"Discovered representative images for {len(candidates)} / {len(all_taxonomy_keys)} taxonomy species."
    )

    # Build structured manifest dictionary (sorted keys for stable diffs)
    manifest_images: dict[str, Any] = {}
    for key in all_taxonomy_keys:
        cand = candidates.get(key)
        if cand:
            manifest_images[key] = {
                "image_url": cand["image_url"],
                "original_class": cand["original_class"],
                "source_dataset": cand["source_dataset"],
            }

    manifest_data = {
        "schema_version": SCHEMA_VERSION,
        "collection": col_name,
        "total_species": len(all_taxonomy_keys),
        "covered_species": len(manifest_images),
        "images": manifest_images,
    }

    # Atomic write to target output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(output_path.parent),
        delete=False,
        suffix=".tmp",
    ) as temp_file:
        temp_name = temp_file.name
        json.dump(manifest_data, temp_file, indent=2, ensure_ascii=False)
        temp_file.flush()
        os.fsync(temp_file.fileno())

    try:
        # Atomic replace
        os.replace(temp_name, output_path)
        print(f"Successfully wrote deterministic manifest to: {output_path}")
    except Exception as e:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
        raise RuntimeError(f"Failed to write manifest: {e}") from e

    return manifest_data


if __name__ == "__main__":
    build_manifest()
