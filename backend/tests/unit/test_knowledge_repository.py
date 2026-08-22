"""
Unit tests for KnowledgeRepository (BGE-M3 Qdrant repository).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.exceptions import (
    QdrantCollectionNotFoundError,
    QdrantSchemaIncompatibleError,
)
from app.repositories.knowledge_repository import (
    KnowledgeRepository,
    get_knowledge_repository,
)


def _make_mock_client():
    client = MagicMock()
    mock_col = MagicMock()
    mock_col.name = "fruvia_knowledge_bge_m3_v1"
    mock_collections_res = MagicMock()
    mock_collections_res.collections = [mock_col]
    client.get_collections.return_value = mock_collections_res

    # Default valid 1024D Cosine info
    mock_info = MagicMock()
    mock_info.points_count = 1500
    mock_info.status.name = "GREEN"
    mock_info.config.params.vectors.size = 1024
    mock_info.config.params.vectors.distance = "Cosine"
    mock_info.payload_schema = {
        "canonical_class": MagicMock(data_type="keyword"),
        "document_type": MagicMock(data_type="keyword"),
    }
    client.get_collection.return_value = mock_info
    return client


def test_knowledge_repository_singleton():
    """Verify get_knowledge_repository returns a singleton instance."""
    r1 = get_knowledge_repository()
    r2 = get_knowledge_repository()
    assert r1 is r2


def test_validate_collection_schema_success():
    """Test successful 1024D Cosine schema validation."""
    client = _make_mock_client()
    repo = KnowledgeRepository(client=client)
    info = repo.validate_collection_schema()

    assert info["collection_name"] == "fruvia_knowledge_bge_m3_v1"
    assert info["vector_size"] == 1024
    assert info["distance"] == "Cosine"
    assert info["points_count"] == 1500


def test_validate_collection_schema_wrong_dimension():
    """Test schema validation rejection on non-1024D vector size."""
    client = _make_mock_client()
    client.get_collection.return_value.config.params.vectors.size = (
        768  # Wrong (768 instead of 1024)
    )

    repo = KnowledgeRepository(client=client)
    with pytest.raises(QdrantSchemaIncompatibleError) as exc_info:
        repo.validate_collection_schema()
    assert "1024D" in str(exc_info.value.message)


def test_validate_collection_schema_wrong_distance():
    """Test schema validation rejection on non-Cosine distance metric."""
    client = _make_mock_client()
    client.get_collection.return_value.config.params.vectors.distance = "Euclid"

    repo = KnowledgeRepository(client=client)
    with pytest.raises(QdrantSchemaIncompatibleError) as exc_info:
        repo.validate_collection_schema()
    assert "Cosine" in str(exc_info.value.message)


def test_validate_collection_schema_unhealthy_status():
    """Test schema validation fails if status is not GREEN or YELLOW."""
    client = _make_mock_client()
    client.get_collection.return_value.status.name = "RED"

    repo = KnowledgeRepository(client=client)
    with pytest.raises(QdrantSchemaIncompatibleError) as exc_info:
        repo.validate_collection_schema()
    assert "RED" in str(exc_info.value.message)


def test_validate_collection_not_found():
    """Test collection not found error handling."""
    client = MagicMock()
    client.get_collection.side_effect = Exception("404 Not Found")

    repo = KnowledgeRepository(client=client)
    with pytest.raises(QdrantCollectionNotFoundError):
        repo.validate_collection_schema()


def test_query_knowledge_success():
    """Test query_knowledge vector search execution with native filters."""
    client = _make_mock_client()
    mock_point = MagicMock()
    mock_point.id = "doc-123"
    mock_point.score = 0.885
    mock_point.payload = {
        "title": "Apple Nutrition",
        "text": "Apples are rich in dietary fiber and vitamin C.",
        "canonical_class": "apple",
        "document_type": "nutrition",
        "source": "usda_fooddata_central",
    }
    client.query_points.return_value.points = [mock_point]

    repo = KnowledgeRepository(client=client)
    query_vec = [0.01] * 1024

    results = repo.query_knowledge(
        vector=query_vec,
        top_k=5,
        canonical_class="apple",
        document_type="nutrition",
    )

    assert len(results) == 1
    assert results[0]["id"] == "doc-123"
    assert results[0]["score"] == 0.885
    assert results[0]["payload"]["title"] == "Apple Nutrition"
    client.query_points.assert_called_once()


def test_query_knowledge_invalid_vector():
    """Test rejection of query vectors with invalid size or NaN values."""
    client = _make_mock_client()
    repo = KnowledgeRepository(client=client)

    # Wrong vector length
    with pytest.raises(ValueError) as exc:
        repo.query_knowledge(vector=[0.1] * 768)
    assert "1024" in str(exc.value)

    # NaN vector
    nan_vec = [0.1] * 1024
    nan_vec[0] = float("nan")
    with pytest.raises(ValueError):
        repo.query_knowledge(vector=nan_vec)
