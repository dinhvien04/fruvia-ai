"""
Unit and integration tests for Backend V2 features:
- Multi-collection architecture & schema validation.
- Native Qdrant filtering with fallback and keyword index safety.
- Rate limiting proxy trust and IP spoofing prevention.
- Timing breakdown and quality metadata.
- Species taxonomy API (/api/species).
- Migration scripts dry-run, UUIDs, atomic checkpoints, and normalization.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.exceptions import QdrantSchemaIncompatibleError
from app.core.rate_limit import InMemorySlidingWindowRateLimiter
from app.main import app
from app.repositories.qdrant_repository import QdrantRepository
from app.schemas.retrieval import RetrievalResult
from app.services.retrieval_service import RetrievalService
from app.utils.taxonomy import get_taxonomy_manager

pytestmark = pytest.mark.unit


class TestConfigAndRateLimitSecurity:
    """Tests for config validation and IP spoofing prevention."""

    def test_settings_threshold_validation(self) -> None:
        # Valid: medium <= high
        s1 = Settings(quality_high_threshold=0.85, quality_medium_threshold=0.70)
        assert s1.quality_medium_threshold == 0.70

        # Invalid: medium > high
        with pytest.raises(ValueError, match="must be <= quality_high_threshold"):
            Settings(quality_high_threshold=0.60, quality_medium_threshold=0.75)

    def test_extract_client_ip_default_no_trust(self) -> None:
        from starlette.requests import Request

        from app.core.rate_limit import extract_client_ip

        # Mock request with spoofed X-Forwarded-For header
        scope = {
            "type": "http",
            "client": ("192.168.1.50", 12345),
            "headers": [(b"x-forwarded-for", b"203.0.113.195, 10.0.0.1")],
        }
        req = Request(scope)

        # By default trust_proxy_headers is False -> peer IP returned
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("TRUST_PROXY_HEADERS", "false")
            from app.core.config import get_settings

            get_settings.cache_clear()
            ip = extract_client_ip(req)
            assert ip == "192.168.1.50"
            get_settings.cache_clear()

    def test_extract_client_ip_with_trusted_proxy(self) -> None:
        from starlette.requests import Request

        from app.core.rate_limit import extract_client_ip

        # Peer is in trusted_proxy_ips; right-to-left traversal extracts client IP
        scope = {
            "type": "http",
            "client": ("127.0.0.1", 12345),
            "headers": [(b"x-forwarded-for", b"203.0.113.195, 10.0.0.1")],
        }
        req = Request(scope)

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("TRUST_PROXY_HEADERS", "true")
            mp.setenv("TRUSTED_PROXY_IPS", "127.0.0.1,::1,10.0.0.1")
            from app.core.config import get_settings

            get_settings.cache_clear()
            ip = extract_client_ip(req)
            assert ip == "203.0.113.195"
            get_settings.cache_clear()

    def test_extract_client_ip_untrusted_peer_ignored(self) -> None:
        from starlette.requests import Request

        from app.core.rate_limit import extract_client_ip

        # Peer is NOT in trusted_proxy_ips even though trust_proxy_headers is true
        scope = {
            "type": "http",
            "client": ("198.51.100.22", 12345),
            "headers": [(b"x-forwarded-for", b"203.0.113.195")],
        }
        req = Request(scope)

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("TRUST_PROXY_HEADERS", "true")
            mp.setenv("TRUSTED_PROXY_IPS", "127.0.0.1,::1")
            from app.core.config import get_settings

            get_settings.cache_clear()
            ip = extract_client_ip(req)
            assert ip == "198.51.100.22"
            get_settings.cache_clear()

    def test_extract_client_ip_empty_trusted_set_fails_closed(self) -> None:
        from starlette.requests import Request

        from app.core.rate_limit import extract_client_ip

        scope = {
            "type": "http",
            "client": ("127.0.0.1", 12345),
            "headers": [(b"x-forwarded-for", b"203.0.113.195")],
        }
        req = Request(scope)

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("TRUST_PROXY_HEADERS", "true")
            mp.setenv("TRUSTED_PROXY_IPS", "")
            from app.core.config import get_settings

            get_settings.cache_clear()
            ip = extract_client_ip(req)
            assert ip == "127.0.0.1"
            get_settings.cache_clear()


class TestMultiCollectionAndSchemaValidation:
    """Tests for multi-collection config override and schema validation."""

    def test_active_gallery_collection_fallback(self) -> None:
        settings = Settings(
            qdrant_collection="fruvia_fruits360_original_dinov2_base_v1",
            fruvia_gallery_collection=None,
        )
        assert settings.active_gallery_collection == "fruvia_fruits360_original_dinov2_base_v1"

    def test_active_gallery_collection_override(self) -> None:
        settings = Settings(
            qdrant_collection="fruvia_fruits360_original_dinov2_base_v1",
            fruvia_gallery_collection="fruvia_gallery_dinov2_base_v2",
        )
        assert settings.active_gallery_collection == "fruvia_gallery_dinov2_base_v2"

    def test_validate_collection_schema_success(self) -> None:
        mock_client = MagicMock()
        mock_info = MagicMock()
        mock_info.config.params.vectors.size = 768
        mock_info.config.params.vectors.distance = "Cosine"
        mock_info.status.name = "GREEN"
        mock_info.points_count = 5000
        mock_client.get_collection.return_value = mock_info

        repo = QdrantRepository(client=mock_client)
        info = repo.validate_collection_schema("fruvia_fruits360_original_dinov2_base_v1")
        assert info["vector_size"] == 768
        assert "Cosine" in info["distance"]
        assert info["points_count"] == 5000
        assert info["status"] == "GREEN"

    def test_validate_collection_schema_dimension_mismatch(self) -> None:
        mock_client = MagicMock()
        mock_info = MagicMock()
        mock_info.config.params.vectors.size = 384
        mock_info.config.params.vectors.distance = "Cosine"
        mock_client.get_collection.return_value = mock_info

        repo = QdrantRepository(client=mock_client)
        with pytest.raises(QdrantSchemaIncompatibleError, match="incompatible with expected 768D"):
            repo.validate_collection_schema("test_coll")

    def test_validate_collection_schema_distance_mismatch(self) -> None:
        mock_client = MagicMock()
        mock_info = MagicMock()
        mock_info.config.params.vectors.size = 768
        mock_info.config.params.vectors.distance = "Euclid"
        mock_client.get_collection.return_value = mock_info

        repo = QdrantRepository(client=mock_client)
        with pytest.raises(
            QdrantSchemaIncompatibleError, match="is incompatible with expected 'Cosine'"
        ):
            repo.validate_collection_schema("test_coll")

    def test_validate_collection_schema_status_red(self) -> None:
        mock_client = MagicMock()
        mock_info = MagicMock()
        mock_info.config.params.vectors.size = 768
        mock_info.config.params.vectors.distance = "Cosine"
        mock_info.status.name = "RED"
        mock_client.get_collection.return_value = mock_info

        repo = QdrantRepository(client=mock_client)
        with pytest.raises(QdrantSchemaIncompatibleError, match="status is RED"):
            repo.validate_collection_schema("test_coll")


class TestNativeQdrantFiltering:
    """Tests for native filter building, keyword index requirements, and fallback handling."""

    def test_get_filter_capabilities_accepts_keyword_only(self) -> None:
        mock_client = MagicMock()
        mock_info = MagicMock()

        schema_cat = MagicMock()
        schema_cat.data_type = "keyword"

        schema_txt = MagicMock()
        schema_txt.data_type = "text"

        mock_info.payload_schema = {
            "category": schema_cat,
            "title": schema_txt,
        }
        mock_client.get_collection.return_value = mock_info

        settings = Settings(native_filter_safe_collections="fruvia_gallery_dinov2_base_v2")
        repo = QdrantRepository(settings=settings, client=mock_client)

        caps = repo.get_filter_capabilities("fruvia_gallery_dinov2_base_v2")
        assert "category" in caps
        assert "title" not in caps  # text must NOT be treated as filter capability

    def test_get_filter_capabilities_unsafe_collection_returns_empty(self) -> None:
        mock_client = MagicMock()
        settings = Settings(native_filter_safe_collections="fruvia_gallery_dinov2_base_v2")
        repo = QdrantRepository(settings=settings, client=mock_client)

        # Legacy collection is not in native_filter_safe_collections
        caps = repo.get_filter_capabilities("fruvia_fruits360_original_dinov2_base_v1")
        assert caps == set()

    def test_build_qdrant_filter_with_supported_fields(self) -> None:
        repo = QdrantRepository(client=MagicMock())
        f = repo.build_qdrant_filter(
            category="fruit",
            canonical_class="apple",
            supported_fields={"category", "canonical_class"},
        )
        assert f is not None
        assert len(f.must) == 2

    def test_build_qdrant_filter_unsupported_fields_filtered_out(self) -> None:
        repo = QdrantRepository(client=MagicMock())
        f = repo.build_qdrant_filter(
            category="fruit",
            canonical_class="apple",
            supported_fields={"category"},
        )
        assert f is not None
        assert len(f.must) == 1
        assert f.must[0].key == "category"

    def test_build_qdrant_filter_all_category(self) -> None:
        repo = QdrantRepository(client=MagicMock())
        f = repo.build_qdrant_filter(category="all", supported_fields={"category"})
        assert f is None


class TestRateLimiterInterface:
    """Tests for pluggable rate limiter."""

    def test_in_memory_sliding_window(self) -> None:
        limiter = InMemorySlidingWindowRateLimiter()
        client_ip = "192.168.1.100"

        allowed, rem = limiter.check_rate_limit(client_ip, limit=2, window_seconds=10.0)
        assert allowed is True
        assert rem == 1

        allowed, rem = limiter.check_rate_limit(client_ip, limit=2, window_seconds=10.0)
        assert allowed is True
        assert rem == 0

        allowed, rem = limiter.check_rate_limit(client_ip, limit=2, window_seconds=10.0)
        assert allowed is False
        assert rem == 0


class TestSpeciesAPI:
    """Integration tests for GET /api/species and GET /api/species/{canonical_class}."""

    def test_list_species_endpoint(self) -> None:
        client = TestClient(app)
        resp = client.get("/api/species")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "items" in data
        assert data["total"] > 0
        assert any(item["canonical_class"] == "apple" for item in data["items"])

    def test_list_species_category_filter(self) -> None:
        client = TestClient(app)
        resp = client.get("/api/species?category=vegetable")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["category"] == "vegetable"

    def test_get_species_detail_found(self) -> None:
        client = TestClient(app)
        resp = client.get("/api/species/durian")
        assert resp.status_code == 200
        data = resp.json()
        assert data["canonical_class"] == "durian"
        assert data["name_en"] == "Durian"
        assert data["name_vi"] == "Sầu riêng"
        assert data["category"] == "fruit"

    def test_get_species_detail_not_found(self) -> None:
        client = TestClient(app)
        resp = client.get("/api/species/non_existent_species_xyz")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_liveness_endpoint(self) -> None:
        client = TestClient(app)
        resp = client.get("/api/live")
        assert resp.status_code == 200
        assert resp.json() == {"status": "live"}


class TestMigrationScriptsLogic:
    """Tests for migration scripts dry-run, UUIDs, atomic checkpoints, and normalization functions."""

    def test_prepare_gallery_v2_payload_normalization(self) -> None:
        from scripts.prepare_gallery_v2 import normalize_point_payload

        tax_mgr = get_taxonomy_manager()
        raw_payload = {
            "original_class": "apple_crimson_snow",
            "image_url": "https://pub-fruits.r2.dev/apple_1.jpg",
            "source_dataset": "fruits360",
            "custom_metadata_tag": "test_tag_123",
        }
        normalized = normalize_point_payload(
            original_payload=raw_payload,
            tax_manager=tax_mgr,
            source_collection="fruvia_fruits360_original_dinov2_base_v1",
            source_point_id=101,
        )

        assert normalized["canonical_class"] == "apple"
        assert normalized["display_name_en"] == "Apple"
        assert normalized["display_name_vi"] == "Táo"
        assert normalized["category"] == "fruit"
        assert normalized["gallery_schema_version"] == 2
        assert normalized["source_collection"] == "fruvia_fruits360_original_dinov2_base_v1"
        assert normalized["source_point_id"] == "101"
        assert normalized["image_url"] == "https://pub-fruits.r2.dev/apple_1.jpg"
        assert normalized["thumbnail_url"] == "https://pub-fruits.r2.dev/apple_1.jpg"
        assert normalized["attributes"].get("custom_metadata_tag") == "test_tag_123"

    def test_prepare_gallery_v2_deterministic_uuids(self) -> None:
        from scripts.prepare_gallery_v2 import generate_deterministic_point_uuid

        uuid_fruits360 = generate_deterministic_point_uuid("fruits360_collection", 1001)
        uuid_packeat = generate_deterministic_point_uuid("packeat_collection", 1001)

        # Same point ID from different source collections MUST produce distinct UUIDs
        assert uuid_fruits360 != uuid_packeat

        # Re-running on same collection and ID must produce identical UUID (idempotency)
        uuid_fruits360_repeat = generate_deterministic_point_uuid("fruits360_collection", 1001)
        assert uuid_fruits360 == uuid_fruits360_repeat

    def test_atomic_checkpoint_persistence_and_validation(self, tmp_path) -> None:
        from scripts.prepare_gallery_v2 import load_checkpoint, save_checkpoint_atomic

        chk_path = tmp_path / "test_migration.checkpoint.json"
        data = {
            "version": 1,
            "source_collection": "coll_a",
            "target_collection": "coll_b",
            "next_offset": 4500,
            "next_offset_type": "int",
            "total_processed": 4500,
            "total_migrated": 4500,
            "total_skipped": 0,
            "batches_completed": 45,
        }
        save_checkpoint_atomic(chk_path, data)
        assert chk_path.exists()

        loaded = load_checkpoint(chk_path, source_collection="coll_a", target_collection="coll_b")
        assert loaded["next_offset"] == 4500
        assert loaded["next_offset_type"] == "int"
        assert loaded["total_migrated"] == 4500

        # Mismatch in source collection should raise RuntimeError
        with pytest.raises(RuntimeError, match="does not match"):
            load_checkpoint(chk_path, source_collection="diff_source", target_collection="coll_b")

    def test_packeat_taxonomy_matching_logic(self) -> None:

        from scripts.build_packeat_taxonomy_mapping import build_taxonomy_index, match_label

        tax_path = Path("configs/taxonomy.yaml")
        canonical_items, alias_map = build_taxonomy_index(tax_path)

        # 1. Exact match
        status, canon, _ = match_label("durian", canonical_items, alias_map)
        assert status == "EXACT"
        assert canon == "durian"

        # 2. Alias match
        status, canon, _ = match_label("pitahaya", canonical_items, alias_map)
        assert status == "ALIAS"
        assert canon == "dragon_fruit"

        # 3. Normalized slug / number stripped match
        status, canon, _ = match_label("apple_red_12", canonical_items, alias_map)
        assert status in ("ALIAS", "NORMALIZED_EXACT")
        assert canon == "apple"

        # 4. Prefix heuristics must require manual review, not auto match
        status, canon, _ = match_label("apple_variety_special_xyz", canonical_items, alias_map)
        assert status == "MANUAL_REVIEW"
        assert canon == "apple"


class TestTimingAndQualityMeta:
    """Tests for retrieval timing breakdown and search quality evaluation."""

    def test_retrieval_service_timing_and_quality(self) -> None:
        mock_encoder = MagicMock()
        mock_encoder.is_loaded = True
        mock_encoder.encode_image.return_value = [0.1] * 768

        mock_repo = MagicMock()
        mock_repo.query_similar.return_value = [
            RetrievalResult(
                original_class="durian",
                canonical_class="durian",
                display_name="Durian",
                filename="durian_1.jpg",
                relative_path="Training/Durian/durian_1.jpg",
                original_split="train",
                similarity=0.88,
            )
        ]

        service = RetrievalService(
            image_encoder=mock_encoder,
            qdrant_repository=mock_repo,
            settings=Settings(quality_high_threshold=0.80, quality_medium_threshold=0.65),
        )

        import io

        from PIL import Image

        img = Image.new("RGB", (100, 100), color="green")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        raw_bytes = buf.getvalue()

        resp = service.retrieve_similar(raw_bytes, filename="test.jpg", top_k=5)

        assert resp.timing is not None
        assert resp.timing.validation_ms >= 0
        assert resp.timing.embedding_ms >= 0
        assert resp.timing.vector_search_ms >= 0
        assert resp.timing.total_ms >= 0
        assert resp.processing_time_ms == resp.timing.total_ms

        assert resp.quality_meta is not None
        assert resp.quality_meta.quality == "high_similarity"
        assert resp.quality_meta.top_similarity == 0.88
