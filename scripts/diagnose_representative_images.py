"""
Diagnostic script for inspecting representative image coverage in Qdrant Gallery collection.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

# Add backend directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.repositories.qdrant_repository import get_qdrant_repository  # noqa: E402
from app.services.representative_image_service import is_safe_image_url  # noqa: E402
from app.utils.taxonomy import get_taxonomy_manager  # noqa: E402


def run_audit():
    settings = get_settings()
    repo = get_qdrant_repository()
    taxonomy = get_taxonomy_manager()
    taxonomy.load()
    client = repo.client
    col = repo.collection_name
    allowed_hosts = settings.allowed_image_host_list or None
    is_prod = settings.is_production

    print("=== QDRANT GALLERY AUDIT ===")
    print(f"Active Collection: {col}")
    caps = repo.get_filter_capabilities(col)
    print(f"Filter Capabilities: {caps}")

    col_info = client.get_collection(col)
    print(f"Total Collection Points: {col_info.points_count}")

    missing_22 = [
        "beetroot",
        "cauliflower",
        "chestnut",
        "chili_pepper",
        "corn",
        "garlic",
        "granadilla",
        "hazelnut",
        "huckleberry",
        "kohlrabi",
        "lettuce",
        "melon",
        "mushroom",
        "peas",
        "pepino",
        "physalis",
        "potato",
        "radish",
        "soursop",
        "spinach",
        "tangerine",
        "walnut",
    ]

    # Map tracking for all 90 taxonomy items
    all_taxonomy_keys = set(taxonomy.taxonomy.keys())
    stats = defaultdict(
        lambda: {
            "matched": 0,
            "with_img": 0,
            "valid_allowed": 0,
            "orig_classes": set(),
            "first_batch_idx": None,
            "sample_url": None,
        }
    )

    offset = None
    batch_size = 500
    max_batches = 200  # Scan up to 100,000 points
    total_scanned = 0

    print(f"\nScanning up to {max_batches * batch_size} points across collection...")

    for batch_idx in range(max_batches):
        pts, offset = client.scroll(
            collection_name=col,
            limit=batch_size,
            offset=offset,
            with_payload=["canonical_class", "original_class", "display_name", "image_url"],
            with_vectors=False,
        )
        if not pts:
            break
        total_scanned += len(pts)

        for p in pts:
            pl = p.payload or {}
            orig = pl.get("original_class") or ""
            raw_c = pl.get("canonical_class")
            disp = pl.get("display_name")
            c_cls, _, _, _ = taxonomy.resolve(
                original_class=orig, payload_canonical=raw_c, payload_display=disp
            )

            raw_url = pl.get("image_url")
            is_safe = is_safe_image_url(raw_url, allowed_hosts=allowed_hosts, is_production=is_prod)

            s = stats[c_cls]
            s["matched"] += 1
            if orig:
                s["orig_classes"].add(orig)
            if raw_url:
                s["with_img"] += 1
            if is_safe:
                s["valid_allowed"] += 1
                if not s["sample_url"]:
                    s["sample_url"] = raw_url
                if s["first_batch_idx"] is None:
                    s["first_batch_idx"] = batch_idx

        if not offset:
            break

    print(f"Total points scanned: {total_scanned} in {batch_idx + 1} batches.\n")

    print(
        f"{'Canonical Class':<15} | {'Matched':<7} | {'With Img':<8} | {'Valid Allowed':<13} | {'First Batch':<11} | {'Original Classes / Diagnosis'}"
    )
    print("-" * 110)

    for cls in missing_22:
        s = stats[cls]
        matched = s["matched"]
        with_img = s["with_img"]
        valid = s["valid_allowed"]
        first_b = str(s["first_batch_idx"]) if s["first_batch_idx"] is not None else "-"
        origs = ", ".join(list(s["orig_classes"])[:3])

        if matched == 0:
            diag = "NO_GALLERY_COVERAGE (0 points in scanned dataset)"
        elif valid == 0:
            diag = "NO_VALID_IMAGE_URL"
        elif s["first_batch_idx"] >= 8:
            diag = f"SCAN_DEPTH_LIMIT (Found at batch {s['first_batch_idx']}, MAX_BOUNDED_SCROLL_BATCHES was 8)"
        else:
            diag = f"FOUND (Batch {s['first_batch_idx']})"

        print(
            f"{cls:<15} | {matched:<7} | {with_img:<8} | {valid:<13} | {first_b:<11} | {origs:<30} | {diag}"
        )

    # Also check total taxonomy coverage
    classes_with_valid_images = [k for k, v in stats.items() if v["valid_allowed"] > 0]
    print(
        f"\nOverall Taxonomy Coverage: {len(classes_with_valid_images)} / {len(all_taxonomy_keys)} species have valid images in the first {total_scanned} points."
    )
    missing_all = all_taxonomy_keys - set(classes_with_valid_images)
    print(f"Species still without images: {sorted(missing_all)}")


if __name__ == "__main__":
    run_audit()
