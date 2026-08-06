"""
Integration tests for POST /api/retrieve endpoint using TestClient.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import QdrantConnectionError
from app.main import app
from app.ml.image_encoder import get_image_encoder
from app.repositories.qdrant_repository import get_qdrant_repository
from app.schemas.retrieval import RetrievalResult
from app.services.retrieval_service import RetrievalService, get_retrieval_service

pytestmark = pytest.mark.integration


class TestRetrievalRoute:
    """Integration tests for POST /api/retrieve endpoint."""

    @pytest.fixture
    def client_with_mocks(self) -> tuple[TestClient, MagicMock, MagicMock]:
        """Provide a TestClient with mocked ImageEncoder and QdrantRepository."""
        mock_encoder = MagicMock()
        mock_encoder.is_loaded = True
        mock_encoder.encode_image.return_value = [0.1] * 768

        mock_repo = MagicMock()
        mock_repo.is_connected.return_value = True
        mock_repo.is_collection_available.return_value = True
        mock_repo.query_similar.return_value = [
            RetrievalResult(
                original_class="Banana",
                filename="banana_01.jpg",
                relative_path="Training/Banana/banana_01.jpg",
                original_split="train",
                similarity=0.9123,
            )
        ]

        app.dependency_overrides[get_image_encoder] = lambda: mock_encoder
        app.dependency_overrides[get_qdrant_repository] = lambda: mock_repo
        app.dependency_overrides[get_retrieval_service] = lambda: RetrievalService(
            image_encoder=mock_encoder,
            qdrant_repository=mock_repo,
        )

        client = TestClient(app)
        yield client, mock_encoder, mock_repo

        app.dependency_overrides.clear()

    def test_retrieve_success(
        self,
        client_with_mocks: tuple[TestClient, MagicMock, MagicMock],
        sample_jpg_bytes: bytes,
    ) -> None:
        """POST /api/retrieve with valid JPEG returns HTTP 200 and RetrievalResponse JSON."""
        client, _, _ = client_with_mocks

        files = {"file": ("fruit.jpg", sample_jpg_bytes, "image/jpeg")}
        data = {"top_k": "5"}

        response = client.post("/api/retrieve", files=files, data=data)

        assert response.status_code == 200
        body = response.json()

        assert "query" in body
        assert body["query"]["filename"] == "fruit.jpg"
        assert "results" in body
        assert body["result_count"] == 1
        assert len(body["results"]) == 1

        first_match = body["results"][0]
        assert first_match["original_class"] == "Banana"
        assert first_match["filename"] == "banana_01.jpg"
        assert first_match["relative_path"] == "Training/Banana/banana_01.jpg"
        assert first_match["original_split"] == "train"
        assert first_match["similarity"] == 0.9123
        assert "processing_time_ms" in body

    def test_retrieve_invalid_top_k(
        self,
        client_with_mocks: tuple[TestClient, MagicMock, MagicMock],
        sample_jpg_bytes: bytes,
    ) -> None:
        """top_k out of range (e.g. 50) returns HTTP 400."""
        client, _, _ = client_with_mocks

        files = {"file": ("fruit.jpg", sample_jpg_bytes, "image/jpeg")}
        data = {"top_k": "50"}  # max allowed is 20

        response = client.post("/api/retrieve", files=files, data=data)

        assert response.status_code == 400
        body = response.json()
        assert body["error"] is True
        assert body["error_code"] == "INVALID_IMAGE"

    def test_retrieve_unsupported_file_extension(
        self,
        client_with_mocks: tuple[TestClient, MagicMock, MagicMock],
    ) -> None:
        """Uploading text file returns HTTP 415 or 400."""
        client, _, _ = client_with_mocks

        files = {"file": ("doc.txt", b"Hello world", "text/plain")}

        response = client.post("/api/retrieve", files=files)

        assert response.status_code in (400, 415)
        body = response.json()
        assert body["error"] is True

    def test_retrieve_corrupt_image(
        self,
        client_with_mocks: tuple[TestClient, MagicMock, MagicMock],
        corrupt_image_bytes: bytes,
    ) -> None:
        """Uploading corrupt image returns HTTP 400."""
        client, _, _ = client_with_mocks

        files = {"file": ("corrupt.jpg", corrupt_image_bytes, "image/jpeg")}

        response = client.post("/api/retrieve", files=files)

        assert response.status_code == 400
        body = response.json()
        assert body["error"] is True
        assert body["error_code"] == "INVALID_IMAGE"

    def test_retrieve_qdrant_unavailable(
        self,
        client_with_mocks: tuple[TestClient, MagicMock, MagicMock],
        sample_jpg_bytes: bytes,
    ) -> None:
        """When Qdrant fails, return HTTP 503."""
        client, _, mock_repo = client_with_mocks
        mock_repo.query_similar.side_effect = QdrantConnectionError(
            message="The image search service is temporarily unavailable.",
            detail="Network error",
        )

        files = {"file": ("fruit.jpg", sample_jpg_bytes, "image/jpeg")}

        response = client.post("/api/retrieve", files=files)

        assert response.status_code == 503
        body = response.json()
        assert body["error"] is True
        assert body["error_code"] == "QDRANT_UNAVAILABLE"
