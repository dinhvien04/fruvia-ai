"""
Unit tests for KnowledgeService.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.core.exceptions import (
    KnowledgeDisabledError,
    KnowledgeValidationError,
)
from app.schemas.knowledge import KnowledgeSearchRequest
from app.services.knowledge_service import KnowledgeService


def test_knowledge_service_disabled_raises():
    """Verify KnowledgeService raises KnowledgeDisabledError when knowledge_enabled=False."""
    settings = Settings(knowledge_enabled=False)
    service = KnowledgeService(settings=settings)

    req = KnowledgeSearchRequest(query="Dragonfruit nutrition")
    with pytest.raises(KnowledgeDisabledError):
        service.search_knowledge(req)

    with pytest.raises(KnowledgeDisabledError):
        service.get_species_knowledge(canonical_class="dragon_fruit")


def test_knowledge_service_empty_query_raises():
    """Verify empty or whitespace query raises KnowledgeValidationError."""
    settings = Settings(knowledge_enabled=True)
    service = KnowledgeService(settings=settings)

    req = KnowledgeSearchRequest(query="   ")
    with pytest.raises(KnowledgeValidationError):
        service.search_knowledge(req)


def test_knowledge_service_search_success():
    """Test successful search_knowledge flow with taxonomy and nutrient metadata."""
    settings = Settings(knowledge_enabled=True)
    mock_encoder = MagicMock()
    mock_encoder.encode_text.return_value = [0.05] * 1024

    mock_repo = MagicMock()
    mock_repo.query_knowledge.return_value = [
        {
            "id": 1,
            "score": 0.9234,
            "payload": {
                "title": "Pitaya (Dragonfruit) Botanical Overview",
                "text": "Pitaya is the fruit of several cactus species.",
                "canonical_class": "dragon_fruit",
                "document_type": "botanical",
                "source": "botanical_guide",
                "nutrients": {
                    "vitamin_c_mg": 20.5,
                    "calories": 60,
                },
                "metadata": {
                    "section": "Characteristics",
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
        query="What is pitaya cactus?",
        top_k=5,
        canonical_class="dragon_fruit",
    )
    resp = service.search_knowledge(req)

    assert resp.query == "What is pitaya cactus?"
    assert resp.result_count == 1
    assert len(resp.results) == 1

    doc = resp.results[0]
    assert doc.id == 1
    assert doc.canonical_class == "dragon_fruit"
    assert doc.title == "Pitaya (Dragonfruit) Botanical Overview"
    assert doc.source == "botanical_guide"
    assert doc.similarity == 0.9234
    assert doc.metadata["nutrients"]["calories"] == 60
    assert doc.metadata["section"] == "Characteristics"
    assert resp.timing is not None
    assert resp.timing.embedding_ms >= 0
    assert resp.timing.vector_search_ms >= 0


def test_knowledge_service_get_species_knowledge():
    """Test get_species_knowledge convenience method."""
    settings = Settings(knowledge_enabled=True)
    mock_encoder = MagicMock()
    mock_encoder.encode_text.return_value = [0.05] * 1024

    mock_repo = MagicMock()
    mock_repo.query_knowledge.return_value = [
        {
            "id": "usda-apple-1",
            "score": 0.95,
            "payload": {
                "title": "Apples, raw, with skin",
                "text": "Nutritional value per 100 g: Energy 52 kcal, Carbohydrates 13.81 g.",
                "canonical_class": "apple",
                "document_type": "nutrition",
                "source": "usda_fooddata_central",
                "nutrients": {"energy_kcal": 52},
            },
        }
    ]

    service = KnowledgeService(
        text_encoder=mock_encoder,
        knowledge_repo=mock_repo,
        settings=settings,
    )

    resp = service.get_species_knowledge(canonical_class="apple", limit=5)

    assert resp.canonical_class == "apple"
    assert resp.display_name == "Apple"
    assert resp.document_count == 1
    assert len(resp.documents) == 1
    assert resp.documents[0].title == "Apples, raw, with skin"
    assert resp.documents[0].metadata["nutrients"]["energy_kcal"] == 52
