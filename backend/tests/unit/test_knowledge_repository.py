"""
Unit tests for KnowledgeRepository (BGE-M3 Qdrant repository).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from qdrant_client.models import FieldCondition, MatchValue

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

    # Default valid 1024D Cosine info with all 3 required keyword indexes
    mock_info = MagicMock()
    mock_info.points_count = 1500
    mock_info.status.name = "GREEN"
    mock_info.config.params.vectors.size = 1024
    mock_info.config.params.vectors.distance = "Cosine"
    mock_info.payload_schema = {
        "canonical_class": MagicMock(data_type="keyword"),
        "document_type": MagicMock(data_type="keyword"),
        "document_id": MagicMock(data_type="keyword"),
    }
    client.get_collection.return_value = mock_info
    return client


def test_knowledge_repository_singleton():
    """Verify get_knowledge_repository returns a singleton instance."""
    r1 = get_knowledge_repository()
    r2 = get_knowledge_repository()
    assert r1 is r2


def test_validate_collection_schema_success():
    """Test successful 1024D Cosine schema and keyword index validation."""
    client = _make_mock_client()
    repo = KnowledgeRepository(client=client)
    info = repo.validate_collection_schema()

    assert info["collection_name"] == "fruvia_knowledge_bge_m3_v1"
    assert info["vector_size"] == 1024
    assert info["distance"] == "Cosine"
    assert info["points_count"] == 1500
    assert "document_id" in info["keyword_indexes"]
    assert "canonical_class" in info["keyword_indexes"]
    assert "document_type" in info["keyword_indexes"]


def test_validate_collection_schema_missing_document_id_index():
    """Test schema validation fails when document_id keyword index is missing."""
    client = _make_mock_client()
    client.get_collection.return_value.payload_schema = {
        "canonical_class": MagicMock(data_type="keyword"),
        "document_type": MagicMock(data_type="keyword"),
        # document_id is missing
    }

    repo = KnowledgeRepository(client=client)
    with pytest.raises(QdrantSchemaIncompatibleError) as exc_info:
        repo.validate_collection_schema()
    assert "missing required keyword payload indexes" in str(exc_info.value.message).lower()
    assert "document_id" in str(exc_info.value.message)


def test_validate_collection_schema_missing_canonical_class_or_document_type_index():
    """Test schema validation fails when canonical_class or document_type keyword index is missing."""
    client = _make_mock_client()
    client.get_collection.return_value.payload_schema = {
        "document_id": MagicMock(data_type="keyword"),
    }

    repo = KnowledgeRepository(client=client)
    with pytest.raises(QdrantSchemaIncompatibleError) as exc_info:
        repo.validate_collection_schema()
    assert "missing required keyword payload indexes" in str(exc_info.value.message).lower()


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


def test_build_qdrant_filter_exact_conditions():
    """Test Qdrant filter building with canonical_class and optional document_type."""
    repo = KnowledgeRepository(client=_make_mock_client())

    # Generic query without document_type
    filter_all = repo.build_qdrant_filter(canonical_class="Apple")
    assert len(filter_all.must) == 1
    assert isinstance(filter_all.must[0], FieldCondition)
    assert filter_all.must[0].key == "canonical_class"
    assert filter_all.must[0].match == MatchValue(value="apple")

    # Specific query with document_type
    filter_typed = repo.build_qdrant_filter(canonical_class="Apple", document_type="Nutrition")
    assert len(filter_typed.must) == 2
    assert filter_typed.must[0].key == "canonical_class"
    assert filter_typed.must[0].match == MatchValue(value="apple")
    assert filter_typed.must[1].key == "document_type"
    assert filter_typed.must[1].match == MatchValue(value="nutrition")


def test_query_knowledge_grouped_success():
    """Test query_knowledge_grouped calls query_points_groups with group_by='document_id' and group_size=1."""
    client = _make_mock_client()

    # Mock GroupedResult
    mock_point1 = MagicMock()
    mock_point1.id = "chunk-1"
    mock_point1.score = 0.912
    mock_point1.payload = {
        "document_id": "wiki-apple",
        "title": "Apple Botanical Overview",
        "text": "The apple is a pome fruit produced by the apple tree.",
        "canonical_class": "apple",
        "document_type": "encyclopedia",
        "source": "wikipedia",
    }

    mock_point2 = MagicMock()
    mock_point2.id = "chunk-5"
    mock_point2.score = 0.875
    mock_point2.payload = {
        "document_id": "usda-apple-101",
        "title": "Apple Nutrition Facts",
        "text": "Apples are high in vitamin C and dietary fiber.",
        "canonical_class": "apple",
        "document_type": "nutrition",
        "source": "usda_fooddata_central",
    }

    group1 = MagicMock()
    group1.id = "wiki-apple"
    group1.hits = [mock_point1]

    group2 = MagicMock()
    group2.id = "usda-apple-101"
    group2.hits = [mock_point2]

    mock_groups_res = MagicMock()
    mock_groups_res.groups = [group1, group2]

    client.query_points_groups.return_value = mock_groups_res

    repo = KnowledgeRepository(client=client)
    query_vec = [0.01] * 1024

    results = repo.query_knowledge_grouped(
        vector=query_vec,
        canonical_class="apple",
        document_type="encyclopedia",
        limit=5,
    )

    assert len(results) == 2
    assert results[0]["document_id"] == "wiki-apple"
    assert results[0]["score"] == 0.912
    assert results[0]["payload"]["title"] == "Apple Botanical Overview"
    assert results[1]["document_id"] == "usda-apple-101"

    # Verify exact Qdrant client call parameters
    client.query_points_groups.assert_called_once()
    call_kwargs = client.query_points_groups.call_args.kwargs
    assert call_kwargs["collection_name"] == "fruvia_knowledge_bge_m3_v1"
    assert call_kwargs["query"] == query_vec
    assert call_kwargs["group_by"] == "document_id"
    assert call_kwargs["group_size"] == 1
    assert call_kwargs["limit"] == 5
    assert call_kwargs["with_payload"] is True
    assert call_kwargs["with_vectors"] is False

    # Verify query_points (ungrouped) was NOT called
    assert not client.query_points.called


def test_zero_mutation_guarantee():
    """Verify runtime KnowledgeRepository has no mutation methods and never calls create/delete/update."""
    client = _make_mock_client()
    repo = KnowledgeRepository(client=client)

    # Verify no collection creation or index creation methods on repo
    assert not hasattr(repo, "create_collection")
    assert not hasattr(repo, "delete_collection")
    assert not hasattr(repo, "create_payload_index")
    assert not hasattr(repo, "upsert_points")

    # Run validation and search to prove zero mutation calls made to client
    repo.validate_collection_schema()
    repo.query_knowledge_grouped(
        vector=[0.05] * 1024,
        canonical_class="apple",
        limit=5,
    )

    assert not client.create_collection.called
    assert not client.delete_collection.called
    assert not client.create_payload_index.called
    assert not client.upsert.called


def test_query_knowledge_invalid_vector():
    """Test rejection of query vectors with invalid size or NaN values."""
    client = _make_mock_client()
    repo = KnowledgeRepository(client=client)

    # Wrong vector length
    with pytest.raises(ValueError) as exc:
        repo.query_knowledge_grouped(vector=[0.1] * 768, canonical_class="apple")
    assert "1024" in str(exc.value)

    # NaN vector
    nan_vec = [0.1] * 1024
    nan_vec[0] = float("nan")
    with pytest.raises(ValueError):
        repo.query_knowledge_grouped(vector=nan_vec, canonical_class="apple")


def test_qdrant_client_supports_query_points_groups_api():
    """Verify that the imported QdrantClient class supports query_points_groups method."""
    import importlib.metadata

    from packaging.version import parse as parse_version
    from qdrant_client import QdrantClient

    # Check method existence on the class
    assert hasattr(QdrantClient, "query_points_groups"), (
        "QdrantClient is missing query_points_groups method required for grouped retrieval"
    )

    # Check installed version satisfies minimum >= 1.11.0
    installed_ver_str = importlib.metadata.version("qdrant-client")
    installed_ver = parse_version(installed_ver_str)
    assert installed_ver >= parse_version("1.11.0"), (
        f"Installed qdrant-client version {installed_ver_str} must be >= 1.11.0"
    )
