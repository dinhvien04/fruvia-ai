"""
Unit tests for QdrantRepository.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.core.exceptions import QdrantCollectionNotFoundError, QdrantConnectionError
from app.repositories.qdrant_repository import QdrantRepository
from app.schemas.retrieval import RetrievalResult

pytestmark = pytest.mark.unit


class TestQdrantRepository:
    """Unit tests for QdrantRepository class."""

    def test_top_k_validation(self) -> None:
        """top_k outside 1..20 must raise ValueError."""
        repo = QdrantRepository(client=MagicMock())
        vector = [0.1] * 768

        with pytest.raises(ValueError, match="top_k must be between 1 and 20"):
            repo.query_similar(vector, top_k=0)

        with pytest.raises(ValueError, match="top_k must be between 1 and 20"):
            repo.query_similar(vector, top_k=21)

    def test_collection_not_found_raises(self) -> None:
        """Missing target collection must raise QdrantCollectionNotFoundError."""
        mock_client = MagicMock()
        mock_collections_res = MagicMock()
        mock_collections_res.collections = []
        mock_client.get_collections.return_value = mock_collections_res

        repo = QdrantRepository(client=mock_client)
        vector = [0.1] * 768

        with pytest.raises(QdrantCollectionNotFoundError, match="is not available"):
            repo.query_similar(vector, top_k=5)

    def test_query_similar_mapping(self) -> None:
        """ScoredPoint items must correctly map to RetrievalResult instances."""
        mock_client = MagicMock()

        # Mock collection check
        mock_col = MagicMock()
        mock_col.name = "fruvia_fruits360_original_dinov2_base_v1"
        mock_collections_res = MagicMock()
        mock_collections_res.collections = [mock_col]
        mock_client.get_collections.return_value = mock_collections_res

        # Mock ScoredPoint search hit
        mock_hit = MagicMock()
        mock_hit.score = 0.9214
        mock_hit.payload = {
            "original_class": "Orange 2",
            "filename": "100_100.jpg",
            "relative_path": "Training/Orange 2/100_100.jpg",
            "original_split": "train",
        }

        # Compatible with query_points / search
        mock_client.search.return_value = [mock_hit]
        mock_query_points_res = MagicMock()
        mock_query_points_res.points = [mock_hit]
        mock_client.query_points.return_value = mock_query_points_res

        repo = QdrantRepository(client=mock_client)
        vector = [0.1] * 768

        results = repo.query_similar(vector, top_k=5)

        assert len(results) == 1
        res = results[0]
        assert isinstance(res, RetrievalResult)
        assert res.original_class == "Orange 2"
        assert res.filename == "100_100.jpg"
        assert res.relative_path == "Training/Orange 2/100_100.jpg"
        assert res.original_split == "train"
        assert res.similarity == 0.9214

    def test_exception_handling_wraps_sdk_error(self) -> None:
        """Qdrant SDK errors during search must be wrapped into QdrantConnectionError."""
        mock_client = MagicMock()

        mock_col = MagicMock()
        mock_col.name = "fruvia_fruits360_original_dinov2_base_v1"
        mock_collections_res = MagicMock()
        mock_collections_res.collections = [mock_col]
        mock_client.get_collections.return_value = mock_collections_res

        # Simulate network timeout / connection failure
        mock_client.search.side_effect = Exception("Connection refused")
        mock_client.query_points.side_effect = Exception("Connection refused")

        settings = Settings()
        repo = QdrantRepository(settings=settings, client=mock_client)
        vector = [0.1] * 768

        with pytest.raises(QdrantConnectionError, match="Failed to query vector database"):
            repo.query_similar(vector, top_k=5)
