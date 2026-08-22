"""
Unit tests for KnowledgeService.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.core.exceptions import (
    KnowledgeDisabledError,
    KnowledgeSpeciesNotFoundError,
    KnowledgeValidationError,
)
from app.schemas.knowledge import KnowledgeSearchRequest
from app.services.knowledge_service import KnowledgeService


def test_knowledge_service_disabled_raises():
    """Verify KnowledgeService raises KnowledgeDisabledError when knowledge_enabled=False."""
    settings = Settings(knowledge_enabled=False)
    service = KnowledgeService(settings=settings)

    req = KnowledgeSearchRequest(query="Dragonfruit nutrition", canonical_class="dragon_fruit")
    with pytest.raises(KnowledgeDisabledError):
        service.search_knowledge(req)

    with pytest.raises(KnowledgeDisabledError):
        service.get_species_knowledge(canonical_class="dragon_fruit")


def test_knowledge_service_empty_query_raises():
    """Verify empty or whitespace query raises KnowledgeValidationError."""
    settings = Settings(knowledge_enabled=True)
    service = KnowledgeService(settings=settings)

    req = KnowledgeSearchRequest(query="   ", canonical_class="apple")
    with pytest.raises(KnowledgeValidationError):
        service.search_knowledge(req)


def test_knowledge_service_unknown_canonical_class_raises_404():
    """Verify search_knowledge and get_species_knowledge raise KnowledgeSpeciesNotFoundError (404) for unknown class."""
    settings = Settings(knowledge_enabled=True)
    mock_encoder = MagicMock()
    mock_repo = MagicMock()

    service = KnowledgeService(
        text_encoder=mock_encoder,
        knowledge_repo=mock_repo,
        settings=settings,
    )

    # 1. POST search request with non-existent class
    req = KnowledgeSearchRequest(
        query="Tell me about kryptonite fruit",
        canonical_class="kryptonite_unknown_specie",
    )
    with pytest.raises(KnowledgeSpeciesNotFoundError) as exc_info:
        service.search_knowledge(req)
    assert exc_info.value.status_code == 404
    assert exc_info.value.error_code == "SPECIES_NOT_FOUND"

    # Verify encoder and Qdrant were NEVER called
    assert not mock_encoder.encode_text.called
    assert not mock_repo.query_knowledge_grouped.called

    # 2. GET species request with non-existent class
    with pytest.raises(KnowledgeSpeciesNotFoundError) as exc_info_get:
        service.get_species_knowledge(canonical_class="kryptonite_unknown_specie")
    assert exc_info_get.value.status_code == 404
    assert not mock_encoder.encode_text.called
    assert not mock_repo.query_knowledge_grouped.called


def test_knowledge_service_real_nutrition_payload_shape():
    """Test real Fruvia Qdrant nutrition records storing nutrients under metadata.nutrients."""
    settings = Settings(knowledge_enabled=True)
    mock_encoder = MagicMock()
    mock_encoder.encode_text.return_value = [0.05] * 1024

    real_nutrients_dict = {
        "Protein": {
            "amount": 0.0859375,
            "unit": "G",
        },
        "Energy": {
            "amount": 52.0,
            "unit": "KCAL",
        },
    }

    mock_repo = MagicMock()
    mock_repo.query_knowledge_grouped.return_value = [
        {
            "id": 501,
            "document_id": "usda-apple-real-1",
            "score": 0.945,
            "payload": {
                "document_id": "usda-apple-real-1",
                "title": "Apples, raw, with skin - Nutrition Facts",
                "text": "Energy 52 kcal per 100g.",
                "canonical_class": "apple",
                "document_type": "nutrition",
                "source": "usda_fooddata_central",
                "metadata": {
                    "nutrients": real_nutrients_dict,
                    "ndb_number": "09003",
                    "dataset_version": "2024-Q1",
                },
            },
        }
    ]

    service = KnowledgeService(
        text_encoder=mock_encoder,
        knowledge_repo=mock_repo,
        settings=settings,
    )

    req = KnowledgeSearchRequest(
        query="What is the protein content of apples?",
        canonical_class="apple",
        document_type="nutrition",
        limit=5,
    )
    resp = service.search_knowledge(req)

    assert resp.result_count == 1
    doc = resp.results[0]
    assert doc.document_id == "usda-apple-real-1"
    # Result exposes nutrients extracted from metadata.nutrients without altering units or values
    assert doc.nutrients == real_nutrients_dict
    assert doc.nutrients["Protein"]["amount"] == 0.0859375
    assert doc.nutrients["Protein"]["unit"] == "G"
    # Full metadata is preserved unchanged
    assert doc.metadata["ndb_number"] == "09003"
    assert doc.metadata["dataset_version"] == "2024-Q1"
    assert doc.metadata["nutrients"] == real_nutrients_dict


def test_knowledge_service_top_level_nutrients_precedence():
    """Test that top-level payload.nutrients takes precedence over metadata.nutrients if both exist."""
    settings = Settings(knowledge_enabled=True)
    mock_encoder = MagicMock()
    mock_encoder.encode_text.return_value = [0.05] * 1024

    top_level_nutrients = {"calories": 100}
    metadata_nutrients = {"calories": 50}

    mock_repo = MagicMock()
    mock_repo.query_knowledge_grouped.return_value = [
        {
            "id": 502,
            "document_id": "doc-precedence-1",
            "score": 0.91,
            "payload": {
                "document_id": "doc-precedence-1",
                "title": "Precedence Test",
                "text": "Sample text",
                "canonical_class": "apple",
                "document_type": "nutrition",
                "nutrients": top_level_nutrients,
                "metadata": {
                    "nutrients": metadata_nutrients,
                    "extra_key": "val",
                },
            },
        }
    ]

    service = KnowledgeService(
        text_encoder=mock_encoder,
        knowledge_repo=mock_repo,
        settings=settings,
    )

    req = KnowledgeSearchRequest(
        query="Calories in apple",
        canonical_class="apple",
    )
    resp = service.search_knowledge(req)
    doc = resp.results[0]
    assert doc.nutrients == {"calories": 100}
    assert doc.metadata["extra_key"] == "val"


def test_knowledge_service_category_fallback_is_other():
    """Test category resolution falls back to 'other' when missing in taxonomy and payload."""
    settings = Settings(knowledge_enabled=True)
    mock_encoder = MagicMock()
    mock_encoder.encode_text.return_value = [0.05] * 1024

    mock_repo = MagicMock()
    mock_repo.query_knowledge_grouped.return_value = [
        {
            "id": 503,
            "document_id": "doc-no-cat",
            "score": 0.85,
            "payload": {
                "document_id": "doc-no-cat",
                "title": "No Category Doc",
                "text": "Sample text",
                "canonical_class": "apple",
                "document_type": "encyclopedia",
                # No category in payload
            },
        }
    ]

    mock_tax_manager = MagicMock()
    mock_tax_item = MagicMock()
    mock_tax_item.name_en = "Apple"
    mock_tax_item.name_vi = "Táo"
    mock_tax_item.category = ""  # Empty category
    mock_tax_manager.get_item.return_value = mock_tax_item

    service = KnowledgeService(
        text_encoder=mock_encoder,
        knowledge_repo=mock_repo,
        taxonomy_manager=mock_tax_manager,
        settings=settings,
    )

    req = KnowledgeSearchRequest(query="Apple info", canonical_class="apple")
    resp = service.search_knowledge(req)
    assert resp.results[0].category == "other"
    assert resp.results[0].category != "fruit"


def test_knowledge_service_request_limits_from_settings():
    """Test that KnowledgeService enforces configured Settings bounds rather than hardcoded limits."""
    custom_settings = Settings(
        knowledge_enabled=True,
        knowledge_max_query_chars=100,
        knowledge_max_top_k=10,
    )
    mock_encoder = MagicMock()
    mock_repo = MagicMock()

    service = KnowledgeService(
        text_encoder=mock_encoder,
        knowledge_repo=mock_repo,
        settings=custom_settings,
    )

    # 1. Query exceeding custom max chars (100)
    long_query = "A" * 101
    req_too_long = KnowledgeSearchRequest(query=long_query, canonical_class="apple")
    with pytest.raises(KnowledgeValidationError) as exc_info:
        service.search_knowledge(req_too_long)
    assert "exceeds maximum character limit" in str(exc_info.value.message)

    # 2. Limit exceeding custom max_top_k (10)
    req_too_many = KnowledgeSearchRequest(query="Apple", canonical_class="apple", limit=15)
    with pytest.raises(KnowledgeValidationError) as exc_info_limit:
        service.search_knowledge(req_too_many)
    assert "exceeds maximum allowed" in str(exc_info_limit.value.message)
