"""
Audit script for full, complete, read-only payload scan of the active Qdrant Gallery collection.

Scans the entire collection until offset is exhausted with `with_vectors=False`.
Resolves canonical classes via TaxonomyManager and evaluates image validity and payload consistency.
"""

from __future__ import annotations

import sys
import time
from collections import defaultdict
from pathlib import Path

# Add backend directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.repositories.qdrant_repository import get_qdrant_repository  # noqa: E402
from app.services.representative_image_service import is_safe_image_url  # noqa: E402
from app.utils.taxonomy import get_taxonomy_manager  # noqa: E402


def run_full_audit():
    settings = get_settings()
    repo = get_qdrant_repository()
    taxonomy = get_taxonomy_manager()
    taxonomy.load()

    client = repo.client
    col = repo.collection_name
    allowed_hosts = settings.allowed_image_host_list or None
    is_prod = settings.is_production

    print("============================================================")
    print("      FRUVIA GALLERY COMPLETE READ-ONLY PAYLOAD AUDIT       ")
    print("============================================================")
    print(f"Active Collection: {col}")
    caps = repo.get_filter_capabilities(col)
    print(f"Filter Capabilities: {caps}")

    col_info = client.get_collection(col)
    total_points_in_col = col_info.points_count
    print(f"Total Collection Points: {total_points_in_col}")

    # Taxonomy classes
    all_taxonomy_keys = set(taxonomy.taxonomy.keys())
    print(f"Total Defined Taxonomy Species: {len(all_taxonomy_keys)}")

    # Statistics structures
    stats = defaultdict(
        lambda: {
            "total_points": 0,
            "with_image_url": 0,
            "valid_allowed_urls": 0,
            "orig_classes": set(),
            "stored_canonical_classes": set(),
            "first_candidate": None,
            "first_point_id": None,
        }
    )

    # Payload health classification counts across entire collection
    payload_health = {
        "correct_canonical": 0,
        "missing_canonical": 0,
        "alias_stored_as_canonical": 0,
        "unknown_canonical": 0,
        "unresolvable": 0,
    }

    batch_size = 2000
    total_scanned = 0
    batch_count = 0
    offset = None

    payload_fields = [
        "canonical_class",
        "original_class",
        "display_name",
        "image_url",
        "source_dataset",
        "dataset_name",
    ]

    start_time = time.time()
    print(f"\nStarting complete payload scan (batch_size={batch_size}, with_vectors=False)...")

    while True:
        pts, offset = client.scroll(
            collection_name=col,
            limit=batch_size,
            offset=offset,
            with_payload=payload_fields,
            with_vectors=False,
        )
        if not pts:
            break

        total_scanned += len(pts)
        batch_count += 1
        if batch_count % 25 == 0 or not offset:
            elapsed = time.time() - start_time
            print(
                f"  Scanned {total_scanned:,} / {total_points_in_col:,} points ({total_scanned / total_points_in_col * 100:.1f}%) in {elapsed:.1f}s..."
            )

        for p in pts:
            pl = p.payload or {}
            orig = pl.get("original_class") or ""
            raw_c = pl.get("canonical_class")
            disp = pl.get("display_name")
            raw_url = pl.get("image_url")
            source_ds = pl.get("source_dataset") or pl.get("dataset_name") or "unknown"
            pt_id = str(p.id)

            # Analyze payload canonical health
            if not raw_c:
                payload_health["missing_canonical"] += 1
            else:
                raw_c_clean = str(raw_c).strip().lower()
                if raw_c_clean in all_taxonomy_keys:
                    payload_health["correct_canonical"] += 1
                elif raw_c_clean in taxonomy._alias_to_canonical:
                    payload_health["alias_stored_as_canonical"] += 1
                else:
                    payload_health["unknown_canonical"] += 1

            # Resolve canonical class via TaxonomyManager
            c_cls, _, _, _ = taxonomy.resolve(
                original_class=orig,
                payload_canonical=raw_c,
                payload_display=disp,
            )

            if not c_cls or c_cls == "unknown":
                payload_health["unresolvable"] += 1

            is_safe = is_safe_image_url(raw_url, allowed_hosts=allowed_hosts, is_production=is_prod)

            s = stats[c_cls]
            s["total_points"] += 1
            if orig:
                s["orig_classes"].add(orig)
            if raw_c:
                s["stored_canonical_classes"].add(str(raw_c))
            if raw_url:
                s["with_image_url"] += 1
            if is_safe:
                s["valid_allowed_urls"] += 1
                if s["first_candidate"] is None:
                    s["first_candidate"] = {
                        "point_id": pt_id,
                        "image_url": raw_url,
                        "original_class": orig,
                        "source_dataset": source_ds,
                    }
                    s["first_point_id"] = pt_id

        if not offset:
            break

    elapsed_total = time.time() - start_time
    print(
        f"\nCompleted scan of {total_scanned:,} points across {batch_count} batches in {elapsed_total:.2f}s."
    )

    print("\n============================================================")
    print("               PAYLOAD HEALTH SUMMARY                       ")
    print("============================================================")
    for k, v in payload_health.items():
        pct = (v / total_scanned * 100) if total_scanned > 0 else 0
        print(f"  {k:<30}: {v:>8,} points ({pct:>5.1f}%)")

    # Group taxonomy species: Available vs Missing
    species_with_valid_images = {
        k: v for k, v in stats.items() if k in all_taxonomy_keys and v["valid_allowed_urls"] > 0
    }
    species_with_no_images = all_taxonomy_keys - set(species_with_valid_images.keys())

    print("\n============================================================")
    print(
        f" TAXONOMY SPECIES COVERAGE: {len(species_with_valid_images)} / {len(all_taxonomy_keys)} AVAILABLE"
    )
    print("============================================================")

    # Detailed table for all 90 species
    print(
        f"\n{'Canonical Class':<20} | {'Points':<7} | {'Valid Imgs':<10} | {'Stored Canonical':<20} | {'Original Classes (sample)'}"
    )
    print("-" * 110)

    for tax_key in sorted(all_taxonomy_keys):
        s = stats[tax_key]
        pts_count = s["total_points"]
        valid_count = s["valid_allowed_urls"]
        stored_c = (
            ", ".join(list(s["stored_canonical_classes"])[:2])
            if s["stored_canonical_classes"]
            else "(none/missing)"
        )
        origs = ", ".join(list(s["orig_classes"])[:3]) if s["orig_classes"] else "(no points)"

        status_flag = "OK" if valid_count > 0 else "NO_IMAGE"
        print(
            f"{tax_key:<20} | {pts_count:<7} | {valid_count:<10} | {stored_c:<20} | {origs:<35} | {status_flag}"
        )

    print("\n============================================================")
    print("          ANALYSIS OF COMMONLY REPORTED SPECIES             ")
    print("============================================================")
    focus_species = [
        "chestnut",
        "chili_pepper",
        "corn",
        "granadilla",
        "melon",
        "peas",
        "pepino",
        "physalis",
        "soursop",
    ]
    for sp in focus_species:
        s = stats[sp]
        print(f"\nSpecies: '{sp}'")
        print(f"  Total Gallery Points       : {s['total_points']}")
        print(f"  Valid Allowed Image URLs   : {s['valid_allowed_urls']}")
        print(f"  Stored Canonical Values    : {list(s['stored_canonical_classes'])}")
        print(f"  Original Classes           : {list(s['orig_classes'])}")
        if s["first_candidate"]:
            print(f"  First Representative Image : {s['first_candidate']['image_url']}")
            print(f"  Source Dataset             : {s['first_candidate']['source_dataset']}")
        else:
            print("  First Representative Image : None (NO_GALLERY_IMAGE_AVAILABLE)")

    print("\n============================================================")
    print("          SPECIES WITH 0 VALID IMAGES (TRUE DATA GAPS)      ")
    print("============================================================")
    for sp in sorted(species_with_no_images):
        s = stats[sp]
        print(f"  - '{sp}': {s['total_points']} points, orig_classes={list(s['orig_classes'])}")

    # Return summary dict for downstream usage
    return {
        "total_scanned": total_scanned,
        "total_taxonomy_species": len(all_taxonomy_keys),
        "species_with_images_count": len(species_with_valid_images),
        "species_without_images_count": len(species_with_no_images),
        "species_without_images": sorted(species_with_no_images),
        "payload_health": payload_health,
        "stats": {
            k: {
                "total_points": v["total_points"],
                "valid_allowed_urls": v["valid_allowed_urls"],
                "orig_classes": list(v["orig_classes"]),
                "stored_canonical_classes": list(v["stored_canonical_classes"]),
                "first_candidate": v["first_candidate"],
            }
            for k, v in stats.items()
            if k in all_taxonomy_keys
        },
    }


if __name__ == "__main__":
    run_full_audit()
