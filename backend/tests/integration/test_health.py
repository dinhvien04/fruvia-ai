"""
Integration tests for the health endpoint.

These tests use FastAPI TestClient with dependency overrides for predictable health statuses.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api import routes_health
from app.main import app
from app.ml.image_encoder import get_image_encoder
from app.repositories.qdrant_repository import get_qdrant_repository

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def reset_health_cache() -> None:
    """Reset the module-level health cache before each test."""
    routes_health._health_cache = None
    routes_health._last_health_check_time = 0.0


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the FastAPI app."""
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for GET /api/health."""

    def test_health_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_health_response_structure(self, client: TestClient) -> None:
        resp = client.get("/api/health")
        data = resp.json()
        assert "status" in data
        assert "model_loaded" in data
        assert "qdrant_connected" in data
        assert "collection_available" in data
        assert "version" in data

    def test_health_status_ok_when_fully_healthy(self) -> None:
        """When encoder and Qdrant are ready, health status should be 'ok'."""
        mock_encoder = MagicMock()
        mock_encoder.is_loaded = True
        mock_repo = MagicMock()
        mock_repo.get_health_status.return_value = (True, True)

        app.dependency_overrides[get_image_encoder] = lambda: mock_encoder
        app.dependency_overrides[get_qdrant_repository] = lambda: mock_repo

        client = TestClient(app)
        resp = client.get("/api/health")
        data = resp.json()

        assert resp.status_code == 200
        assert data["status"] == "ok"
        assert data["model_loaded"] is True
        assert data["qdrant_connected"] is True
        assert data["collection_available"] is True

        app.dependency_overrides.clear()

    def test_health_status_degraded_when_qdrant_offline(self) -> None:
        """When Qdrant is offline, status should be 'degraded'."""
        mock_encoder = MagicMock()
        mock_encoder.is_loaded = True
        mock_repo = MagicMock()
        mock_repo.get_health_status.return_value = (False, False)

        app.dependency_overrides[get_image_encoder] = lambda: mock_encoder
        app.dependency_overrides[get_qdrant_repository] = lambda: mock_repo

        client = TestClient(app)
        resp = client.get("/api/health")
        data = resp.json()

        assert resp.status_code == 200
        assert data["status"] == "degraded"
        assert data["model_loaded"] is True
        assert data["qdrant_connected"] is False
        assert data["collection_available"] is False

        app.dependency_overrides.clear()
