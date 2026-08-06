"""
Unit tests for RetrievalService.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.exceptions import ImageValidationError, UnsupportedFormatError
from app.schemas.retrieval import RetrievalResponse, RetrievalResult
from app.services.retrieval_service import RetrievalService

pytestmark = pytest.mark.unit


class TestRetrievalService:
    """Unit tests for RetrievalService class."""

    def test_retrieve_similar_success(self, sample_jpg_bytes: bytes) -> None:
        """Valid image bytes and parameters should return a RetrievalResponse."""
        mock_encoder = MagicMock()
        mock_encoder.encode_image.return_value = [0.1] * 768

        mock_repo = MagicMock()
        mock_repo.query_similar.return_value = [
            RetrievalResult(
                original_class="Apple Braeburn",
                filename="0_100.jpg",
                relative_path="Training/Apple Braeburn/0_100.jpg",
                original_split="train",
                similarity=0.95,
            )
        ]

        service = RetrievalService(
            image_encoder=mock_encoder,
            qdrant_repository=mock_repo,
        )

        response = service.retrieve_similar(
            file_bytes=sample_jpg_bytes,
            filename="test_apple.jpg",
            top_k=5,
        )

        assert isinstance(response, RetrievalResponse)
        assert response.query.filename == "test_apple.jpg"
        assert response.result_count == 1
        assert len(response.results) == 1
        assert response.results[0].original_class == "Apple Braeburn"
        assert response.results[0].similarity == 0.95
        assert response.processing_time_ms >= 0.0

        mock_encoder.encode_image.assert_called_once()
        mock_repo.query_similar.assert_called_once_with(vector=[0.1] * 768, top_k=5)

    def test_retrieve_unsupported_format_raises(self, non_image_bytes: bytes) -> None:
        """Non-image bytes with invalid extension should raise UnsupportedFormatError."""
        mock_encoder = MagicMock()
        mock_repo = MagicMock()

        service = RetrievalService(
            image_encoder=mock_encoder,
            qdrant_repository=mock_repo,
        )

        with pytest.raises(UnsupportedFormatError):
            service.retrieve_similar(
                file_bytes=non_image_bytes,
                filename="document.txt",
                top_k=5,
            )

    def test_retrieve_corrupt_image_raises(self, corrupt_image_bytes: bytes) -> None:
        """Corrupt image content should raise ImageValidationError."""
        mock_encoder = MagicMock()
        mock_repo = MagicMock()

        service = RetrievalService(
            image_encoder=mock_encoder,
            qdrant_repository=mock_repo,
        )

        with pytest.raises(ImageValidationError):
            service.retrieve_similar(
                file_bytes=corrupt_image_bytes,
                filename="corrupt.jpg",
                top_k=5,
            )
