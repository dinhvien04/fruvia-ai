"""
Integration tests for Knowledge API endpoints.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.ml.text_encoder import get_text_encoder
from app.repositories.knowledge_repository import get_knowledge_repository
from app.services.knowledge_service import KnowledgeService, get_knowledge_service

pytestmark = pytest.mark.integration


@pytest.fixture
def client_with_knowledge_mocks():
    """Provide a TestClient with mocked BGE-M3 TextEncoder and KnowledgeRepository."""
    mock_encoder = MagicMock()
    mock_encoder.is_loaded = True
    mock_encoder.encode_text.return_value = [0.05] * 1024

    mock_repo = MagicMock()
    mock_repo.is_connected.return_value = True
    mock_repo.is_collection_available.return_value = True

    # Real Fruvia Qdrant payload shape with metadata.nutrients
    mock_repo.query_knowledge_grouped.return_value = [
        {
            "id": "doc-apple-usda",
            "document_id": "usda-apple-001",
            "score": 0.912,
            "payload": {
                "document_id": "usda-apple-001",
                "title": "Apple Nutrition Facts",
                "text": "Apples contain dietary fiber, potassium, and antioxidants.",
                "canonical_class": "apple",
                "document_type": "nutrition",
                "source": "usda_fooddata_central",
                "source_dataset": "usda_fdc_2024",
                "language": "en",
                "source_url": "https://fdc.nal.usda.gov/fdc-app.html#/food-details/171688/nutrients",
                "scientific_name": "Malus domestica",
                "metadata": {
                    "nutrients": {
                        "Protein": {
                            "amount": 0.0859375,
                            "unit": "G",
                        },
                        "Energy": {
                            "amount": 52.0,
                            "unit": "KCAL",
                        },
                    },
                    "ndb_number": "09003",
                },
                "taxonomy": {
                    "genus": "Malus",
                    "family": "Rosaceae",
                },
            },
        }
    ]

    settings = Settings(knowledge_enabled=True)
    service = KnowledgeService(
        text_encoder=mock_encoder,
        knowledge_repo=mock_repo,
        settings=settings,
    )

    app.dependency_overrides[get_text_encoder] = lambda: mock_encoder
    app.dependency_overrides[get_knowledge_repository] = lambda: mock_repo
    app.dependency_overrides[get_knowledge_service] = lambda: service

    client = TestClient(app)
    yield client, mock_encoder, mock_repo

    app.dependency_overrides.clear()


def test_post_knowledge_search_grouped_success(client_with_knowledge_mocks):
    """POST /api/knowledge/search returns HTTP 200 with grouped search results and metadata.nutrients."""
    client, _, _ = client_with_knowledge_mocks

    payload = {
        "query": "What vitamins are in apples?",
        "canonical_class": "apple",
        "document_type": "nutrition",
        "limit": 5,
    }
    response = client.post("/api/knowledge/search", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["query"] == "What vitamins are in apples?"
    assert data["canonical_class"] == "apple"
    assert data["document_type"] == "nutrition"
    assert data["result_count"] == 1
    assert len(data["results"]) == 1

    doc = data["results"][0]
    assert doc["document_id"] == "usda-apple-001"
    assert doc["title"] == "Apple Nutrition Facts"
    assert doc["source"] == "usda_fooddata_central"
    assert doc["source_dataset"] == "usda_fdc_2024"
    assert doc["language"] == "en"
    assert (
        doc["source_url"] == "https://fdc.nal.usda.gov/fdc-app.html#/food-details/171688/nutrients"
    )
    assert doc["scientific_name"] == "Malus domestica"
    assert doc["score"] == 0.912
    # Verify real nutrient payload format exposed under doc.nutrients
    assert doc["nutrients"]["Protein"]["amount"] == 0.0859375
    assert doc["nutrients"]["Protein"]["unit"] == "G"
    assert doc["nutrients"]["Energy"]["amount"] == 52.0
    assert doc["taxonomy"]["genus"] == "Malus"
    # Never expose vector in API response
    assert "vector" not in doc
    assert "embedding" not in doc


def test_post_knowledge_search_unknown_species_returns_404(client_with_knowledge_mocks):
    """POST /api/knowledge/search returns HTTP 404 and does NOT call encoder/qdrant for unknown species."""
    client, mock_encoder, mock_repo = client_with_knowledge_mocks

    payload = {
        "query": "What is kryptonite fruit?",
        "canonical_class": "unknown_kryptonite_fruit",
    }
    response = client.post("/api/knowledge/search", json=payload)
    assert response.status_code == 404
    data = response.json()
    assert data["error"] is True
    assert data["error_code"] == "SPECIES_NOT_FOUND"

    assert not mock_encoder.encode_text.called
    assert not mock_repo.query_knowledge_grouped.called


def test_get_species_knowledge_unknown_species_returns_404(client_with_knowledge_mocks):
    """GET /api/species/{canonical_class}/knowledge returns HTTP 404 and does NOT call encoder/qdrant for unknown species."""
    client, mock_encoder, mock_repo = client_with_knowledge_mocks

    response = client.get("/api/species/unknown_kryptonite_fruit/knowledge")
    assert response.status_code == 404
    data = response.json()
    assert data["error"] is True
    assert data["error_code"] == "SPECIES_NOT_FOUND"

    assert not mock_encoder.encode_text.called
    assert not mock_repo.query_knowledge_grouped.called


def test_post_knowledge_search_disabled():
    """POST /api/knowledge/search returns HTTP 503 when knowledge is disabled."""
    settings = Settings(knowledge_enabled=False)
    service = KnowledgeService(settings=settings)

    app.dependency_overrides[get_knowledge_service] = lambda: service
    client = TestClient(app)

    try:
        response = client.post(
            "/api/knowledge/search",
            json={"query": "Apple", "canonical_class": "apple"},
        )
        assert response.status_code == 503
        data = response.json()
        assert data["error"] is True
        assert data["error_code"] == "KNOWLEDGE_SERVICE_DISABLED"
    finally:
        app.dependency_overrides.clear()


def test_get_species_knowledge_endpoint(client_with_knowledge_mocks):
    """GET /api/species/{canonical_class}/knowledge returns species nutrition & facts."""
    client, _, _ = client_with_knowledge_mocks

    response = client.get("/api/species/apple/knowledge?limit=5")
    assert response.status_code == 200

    data = response.json()
    assert data["canonical_class"] == "apple"
    assert data["display_name"] == "Apple"
    assert data["document_count"] == 1
    assert len(data["documents"]) == 1
    assert data["documents"][0]["document_id"] == "usda-apple-001"
    assert data["documents"][0]["title"] == "Apple Nutrition Facts"
    assert data["documents"][0]["nutrients"]["Protein"]["amount"] == 0.0859375
