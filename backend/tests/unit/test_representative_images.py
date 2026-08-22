"""
Unit and integration tests for RepresentativeImageService, CSP headers, and /api/species representative image layer.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app, create_app
from app.services.representative_image_service import (
    RepresentativeImageService,
    is_safe_image_url,
)
from app.utils.taxonomy import TaxonomyItem


def test_is_safe_image_url():
    """Verify URL validation rejects unsafe schemes and non-allowed hosts."""
    assert (
        is_safe_image_url("https://pub-8ee1729b06674ae5b328c4d21021eac3.r2.dev/thumbnails/123.webp")
        is True
    )
    assert is_safe_image_url("http://example.com/image.jpg") is True

    # Unsafe schemes
    assert is_safe_image_url("javascript:alert(1)") is False
    assert is_safe_image_url("data:image/png;base64,123") is False
    assert is_safe_image_url("file:///etc/passwd") is False
    assert is_safe_image_url("vbscript:msgbox") is False
    assert is_safe_image_url("") is False
    assert is_safe_image_url(None) is False
    assert is_safe_image_url("/relative/path.jpg") is False

    # Allowed hosts check
    allowed = ["r2.dev", "fruvia.ai"]
    assert is_safe_image_url("https://pub-123.r2.dev/img.jpg", allowed_hosts=allowed) is True
    assert is_safe_image_url("https://fruvia.ai/img.jpg", allowed_hosts=allowed) is True
    assert is_safe_image_url("https://cdn.fruvia.ai/img.jpg", allowed_hosts=allowed) is True
    assert is_safe_image_url("https://evil.com/img.jpg", allowed_hosts=allowed) is False

    # Production fail-closed when allowed_hosts is empty
    assert (
        is_safe_image_url("https://cdn.external.com/img.jpg", allowed_hosts=[], is_production=True)
        is False
    )
    assert (
        is_safe_image_url("http://localhost:8000/img.jpg", allowed_hosts=[], is_production=True)
        is True
    )


def test_representative_image_service_caching():
    """Verify RepresentativeImageService uses manifest first, and falls back to Qdrant if manifest is absent."""
    mock_qdrant_repo = MagicMock()
    mock_client = MagicMock()
    mock_qdrant_repo.client = mock_client
    mock_qdrant_repo.collection_name = "test_collection"
    mock_qdrant_repo.get_filter_capabilities.return_value = set()

    # Mock scroll result returning apple point
    mock_point = MagicMock()
    mock_point.payload = {
        "canonical_class": "apple",
        "original_class": "Apple 1",
        "display_name": "Apple",
        "image_url": "https://pub-8ee1729b06674ae5b328c4d21021eac3.r2.dev/thumbnails/apple.webp",
    }
    mock_client.scroll.return_value = ([mock_point], None)

    mock_tax_mgr = MagicMock()
    mock_tax_mgr.taxonomy = {
        "apple": TaxonomyItem(
            canonical_class="apple", name_en="Apple", name_vi="Táo", category="fruit", is_fruit=True
        ),
        "banana": TaxonomyItem(
            canonical_class="banana",
            name_en="Banana",
            name_vi="Chuối",
            category="fruit",
            is_fruit=True,
        ),
    }
    mock_tax_mgr.resolve.return_value = ("apple", "Apple", "Táo", "fruit")

    # Service with missing manifest path -> uses Qdrant fallback
    from pathlib import Path

    service = RepresentativeImageService(
        manifest_path=Path("non_existent_manifest.json"),
        qdrant_repo=mock_qdrant_repo,
        taxonomy_manager=mock_tax_mgr,
        ttl_seconds=300.0,
    )

    # First call: triggers single bounded scroll
    images1 = service.get_representative_images(["apple", "banana"])
    assert (
        images1["apple"]
        == "https://pub-8ee1729b06674ae5b328c4d21021eac3.r2.dev/thumbnails/apple.webp"
    )
    assert images1["banana"] is None
    assert mock_client.scroll.call_count == 1

    # Second call: uses in-memory cache, no new scroll calls
    images2 = service.get_representative_images(["apple", "banana"])
    assert images2 == images1
    assert mock_client.scroll.call_count == 1


def test_representative_image_service_indexed_match_any():
    """Verify service uses MatchAny filter when canonical_class keyword index is available."""
    mock_qdrant_repo = MagicMock()
    mock_client = MagicMock()
    mock_qdrant_repo.client = mock_client
    mock_qdrant_repo.collection_name = "fruvia_gallery_dinov2_base_v2"
    mock_qdrant_repo.get_filter_capabilities.return_value = {"canonical_class"}

    mock_point = MagicMock()
    mock_point.payload = {
        "canonical_class": "apple",
        "original_class": "Apple 1",
        "image_url": "https://pub-8ee1729b06674ae5b328c4d21021eac3.r2.dev/apple.webp",
    }
    mock_client.scroll.return_value = ([mock_point], None)

    mock_tax_mgr = MagicMock()
    mock_tax_mgr.taxonomy = {
        "apple": TaxonomyItem(
            canonical_class="apple", name_en="Apple", name_vi="Táo", category="fruit", is_fruit=True
        ),
    }
    mock_tax_mgr.resolve.return_value = ("apple", "Apple", "Táo", "fruit")

    from pathlib import Path

    service = RepresentativeImageService(
        manifest_path=Path("non_existent_manifest.json"),
        qdrant_repo=mock_qdrant_repo,
        taxonomy_manager=mock_tax_mgr,
        ttl_seconds=300.0,
    )

    images = service.get_representative_images(["apple"])
    assert images["apple"] == "https://pub-8ee1729b06674ae5b328c4d21021eac3.r2.dev/apple.webp"
    assert mock_client.scroll.call_count == 1
    # Check that scroll_filter was passed
    call_kwargs = mock_client.scroll.call_args.kwargs
    assert "scroll_filter" in call_kwargs
    assert call_kwargs["scroll_filter"] is not None


def test_representative_image_service_scans_past_null_images():
    """Verify that service scans past points with null/invalid image_url until valid image found."""
    mock_qdrant_repo = MagicMock()
    mock_client = MagicMock()
    mock_qdrant_repo.client = mock_client
    mock_qdrant_repo.collection_name = "test_collection"
    mock_qdrant_repo.get_filter_capabilities.return_value = set()

    # Point 1 has null image_url, Point 2 has unsafe url, Point 3 has valid url
    pt1 = MagicMock()
    pt1.payload = {
        "canonical_class": "apple",
        "original_class": "Apple 1",
        "image_url": None,
    }
    pt2 = MagicMock()
    pt2.payload = {
        "canonical_class": "apple",
        "original_class": "Apple 2",
        "image_url": "javascript:alert(1)",
    }
    pt3 = MagicMock()
    pt3.payload = {
        "canonical_class": "apple",
        "original_class": "Apple 3",
        "image_url": "https://pub-8ee1729b06674ae5b328c4d21021eac3.r2.dev/apple.webp",
    }

    mock_client.scroll.return_value = ([pt1, pt2, pt3], None)

    mock_tax_mgr = MagicMock()
    mock_tax_mgr.taxonomy = {
        "apple": TaxonomyItem(
            canonical_class="apple", name_en="Apple", name_vi="Táo", category="fruit", is_fruit=True
        ),
    }
    mock_tax_mgr.resolve.return_value = ("apple", "Apple", "Táo", "fruit")

    from pathlib import Path

    service = RepresentativeImageService(
        manifest_path=Path("non_existent_manifest.json"),
        qdrant_repo=mock_qdrant_repo,
        taxonomy_manager=mock_tax_mgr,
        ttl_seconds=300.0,
    )

    images = service.get_representative_images(["apple"])
    assert images["apple"] == "https://pub-8ee1729b06674ae5b328c4d21021eac3.r2.dev/apple.webp"


def test_representative_image_service_qdrant_down_resilience_and_no_negative_cache():
    """Verify that if Qdrant fails, service returns None and does not cache negative result."""
    mock_qdrant_repo = MagicMock()
    mock_client = MagicMock()
    mock_qdrant_repo.client = mock_client
    mock_qdrant_repo.collection_name = "test_collection"
    mock_qdrant_repo.get_filter_capabilities.return_value = set()
    mock_client.scroll.side_effect = Exception("Qdrant unreachable")

    mock_tax_mgr = MagicMock()
    mock_tax_mgr.taxonomy = {
        "apple": TaxonomyItem(
            canonical_class="apple", name_en="Apple", name_vi="Táo", category="fruit", is_fruit=True
        ),
    }

    service = RepresentativeImageService(
        manifest_path=Path("non_existent_manifest.json"),
        qdrant_repo=mock_qdrant_repo,
        taxonomy_manager=mock_tax_mgr,
    )

    images = service.get_representative_images(["apple"])
    assert images.get("apple") is None
    # Fallback cache should NOT hold negative result
    assert "apple" not in service._fallback_cache


def test_csp_header_matches_allowed_image_hosts(monkeypatch):
    """Verify that SecurityHeadersMiddleware injects ALLOWED_IMAGE_HOSTS into CSP img-src."""
    monkeypatch.setenv("ALLOWED_IMAGE_HOSTS", "images.example.com,pub-123.r2.dev")
    get_settings.cache_clear()

    test_app = create_app()
    client = TestClient(test_app)

    response = client.get("/explore")
    assert response.status_code == 200
    csp = response.headers.get("Content-Security-Policy", "")

    # Must contain both allowed hosts in img-src
    assert "img-src 'self' data: https://images.example.com https://pub-123.r2.dev;" in csp or (
        "https://images.example.com" in csp and "https://pub-123.r2.dev" in csp
    )
    assert "evil.example" not in csp

    get_settings.cache_clear()


def test_csp_header_empty_allowed_hosts(monkeypatch):
    """Verify that CSP img-src is restricted to 'self' data: when ALLOWED_IMAGE_HOSTS is empty."""
    monkeypatch.setenv("ALLOWED_IMAGE_HOSTS", "")
    get_settings.cache_clear()

    test_app = create_app()
    client = TestClient(test_app)

    response = client.get("/explore")
    assert response.status_code == 200
    csp = response.headers.get("Content-Security-Policy", "")

    assert "img-src 'self' data:;" in csp
    assert "r2.dev" not in csp
    assert "evil.example" not in csp

    get_settings.cache_clear()


def test_api_species_includes_representative_image_url():
    """Verify GET /api/species and GET /api/species/{canonical_class} return representative_image_url field."""
    client = TestClient(app)

    response = client.get("/api/species")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "items" in data
    assert len(data["items"]) > 0

    first_item = data["items"][0]
    assert "canonical_class" in first_item
    assert "name_en" in first_item
    assert "name_vi" in first_item
    assert "category" in first_item
    assert "is_fruit" in first_item
    assert "aliases" in first_item
    assert "representative_image_url" in first_item

    # Detail route
    detail_res = client.get(f"/api/species/{first_item['canonical_class']}")
    assert detail_res.status_code == 200
    detail_data = detail_res.json()
    assert detail_data["canonical_class"] == first_item["canonical_class"]
    assert "representative_image_url" in detail_data


def test_api_species_unknown_returns_404():
    """Verify GET /api/species/unknown_invalid_fruit returns 404."""
    client = TestClient(app)
    response = client.get("/api/species/unknown_invalid_fruit_12345")
    assert response.status_code == 404


def test_taxonomy_alias_resolution_for_gallery_species():
    """Verify that previously missing species with aliases now resolve cleanly via TaxonomyManager."""
    from app.utils.taxonomy import get_taxonomy_manager

    tax_mgr = get_taxonomy_manager()
    tax_mgr.load()

    test_cases = [
        ("Corn Kernel", "corn"),
        ("Corn Husk", "corn"),
        ("Grenadilla", "granadilla"),
        ("Pea", "peas"),
        ("Melon Pear", "pepino"),
        ("Physalis with Husk", "physalis"),
        ("Cape Gooseberry", "physalis"),
        ("Mountain Soursop", "soursop"),
        ("Guanabana", "soursop"),
        ("Muskmelon", "melon"),
        ("Galia Melon", "melon"),
        ("Horned Melon", "melon"),
        ("Melon Piel de Sapo", "melon"),
        ("Jalapeno", "chili_pepper"),
        ("Chili", "chili_pepper"),
    ]

    for raw_label, expected_canonical in test_cases:
        canonical, _, _, _ = tax_mgr.resolve(original_class=raw_label)
        assert canonical == expected_canonical, (
            f"Expected '{raw_label}' to resolve to '{expected_canonical}', got '{canonical}'"
        )


def test_representative_image_manifest_loading_and_runtime_validation(tmp_path):
    """Verify RepresentativeImageService loads manifest JSON and validates URL security at runtime."""
    manifest_file = tmp_path / "test_manifest.json"
    manifest_content = {
        "schema_version": 1,
        "collection": "test_col",
        "total_species": 3,
        "covered_species": 3,
        "images": {
            "apple": {
                "image_url": "https://pub-8ee1729b06674ae5b328c4d21021eac3.r2.dev/apple.webp",
                "original_class": "apple",
                "source_dataset": "fruits262",
            },
            "corn": {
                "image_url": "https://pub-8ee1729b06674ae5b328c4d21021eac3.r2.dev/corn.webp",
                "original_class": "corn kernel",
                "source_dataset": "fruits262",
            },
            "unsafe_species": {
                "image_url": "javascript:alert(1)",
                "original_class": "unsafe",
                "source_dataset": "evil",
            },
        },
    }
    import json

    manifest_file.write_text(json.dumps(manifest_content), encoding="utf-8")

    mock_tax_mgr = MagicMock()
    mock_tax_mgr.taxonomy = {
        "apple": TaxonomyItem(
            canonical_class="apple", name_en="Apple", name_vi="Táo", category="fruit", is_fruit=True
        ),
        "corn": TaxonomyItem(
            canonical_class="corn", name_en="Corn", name_vi="Bắp", category="seed", is_fruit=False
        ),
        "unsafe_species": TaxonomyItem(
            canonical_class="unsafe_species",
            name_en="Unsafe",
            name_vi="Không an toàn",
            category="other",
            is_fruit=False,
        ),
        "chestnut": TaxonomyItem(
            canonical_class="chestnut",
            name_en="Chestnut",
            name_vi="Hạt dẻ",
            category="nut",
            is_fruit=False,
        ),
    }

    mock_qdrant_repo = MagicMock()

    service = RepresentativeImageService(
        manifest_path=manifest_file,
        qdrant_repo=mock_qdrant_repo,
        taxonomy_manager=mock_tax_mgr,
    )

    # 1. Manifest loaded successfully
    assert service._manifest_loaded is True

    # 2. Lookup for manifest items is O(1) without Qdrant calls
    images = service.get_representative_images(["apple", "corn", "unsafe_species"])
    assert images["apple"] == "https://pub-8ee1729b06674ae5b328c4d21021eac3.r2.dev/apple.webp"
    assert images["corn"] == "https://pub-8ee1729b06674ae5b328c4d21021eac3.r2.dev/corn.webp"
    # Unsafe URL rejected by runtime validation
    assert images["unsafe_species"] is None
    # Qdrant was NOT called for species present in manifest
    assert mock_qdrant_repo.client.scroll.call_count == 0


def test_manifest_generator_alias_resolution_logic(tmp_path):
    """Verify build_manifest correctly resolves points with aliases and missing canonical fields."""
    from scripts.build_representative_image_manifest import build_manifest

    # Mock Qdrant points with varying payloads
    pt_corn = MagicMock()
    pt_corn.id = "00000000-0000-0000-0000-000000000001"
    pt_corn.payload = {
        "original_class": "Corn Kernel",
        "canonical_class": None,
        "image_url": "https://pub-8ee1729b06674ae5b328c4d21021eac3.r2.dev/corn.webp",
        "source_dataset": "fruits262",
    }

    pt_chili = MagicMock()
    pt_chili.id = "00000000-0000-0000-0000-000000000002"
    pt_chili.payload = {
        "original_class": "Jalapeno",
        "canonical_class": "jalapeno",
        "image_url": "https://pub-8ee1729b06674ae5b328c4d21021eac3.r2.dev/jalapeno.webp",
        "source_dataset": "fruits262",
    }

    pt_apple = MagicMock()
    pt_apple.id = "00000000-0000-0000-0000-000000000003"
    pt_apple.payload = {
        "original_class": "Apple 1",
        "canonical_class": "apple",
        "image_url": "https://pub-8ee1729b06674ae5b328c4d21021eac3.r2.dev/apple.webp",
        "source_dataset": "fruits-360",
    }

    mock_client = MagicMock()
    mock_client.scroll.side_effect = [
        ([pt_corn, pt_chili, pt_apple], None),
    ]

    mock_qdrant_repo = MagicMock()
    mock_qdrant_repo.client = mock_client
    mock_qdrant_repo.collection_name = "test_collection"

    out_file = tmp_path / "gen_manifest.json"

    with MagicMock() as mock_settings:
        mock_settings.allowed_image_host_list = ["r2.dev"]
        mock_settings.is_production = False

        from unittest.mock import patch

        with (
            patch(
                "scripts.build_representative_image_manifest.get_qdrant_repository",
                return_value=mock_qdrant_repo,
            ),
            patch(
                "scripts.build_representative_image_manifest.get_settings",
                return_value=mock_settings,
            ),
        ):
            manifest_data = build_manifest(output_path=out_file, early_exit_if_all_found=False)

    assert manifest_data["schema_version"] == 1
    assert "corn" in manifest_data["images"]
    assert (
        manifest_data["images"]["corn"]["image_url"]
        == "https://pub-8ee1729b06674ae5b328c4d21021eac3.r2.dev/corn.webp"
    )

    assert "chili_pepper" in manifest_data["images"]
    assert (
        manifest_data["images"]["chili_pepper"]["image_url"]
        == "https://pub-8ee1729b06674ae5b328c4d21021eac3.r2.dev/jalapeno.webp"
    )

    assert "apple" in manifest_data["images"]
    assert (
        manifest_data["images"]["apple"]["image_url"]
        == "https://pub-8ee1729b06674ae5b328c4d21021eac3.r2.dev/apple.webp"
    )

    # Verify JSON file exists and is valid JSON
    assert out_file.exists()
    import json

    loaded = json.loads(out_file.read_text(encoding="utf-8"))
    assert loaded == manifest_data
