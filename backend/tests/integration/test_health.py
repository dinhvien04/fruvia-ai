"""
Integration tests for the health endpoint.

These tests use FastAPI TestClient — no external services required.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.integration


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
        assert "version" in data

    def test_health_status_ok(self, client: TestClient) -> None:
        resp = client.get("/api/health")
        data = resp.json()
        assert data["status"] == "ok"

    def test_health_model_not_loaded_yet(self, client: TestClient) -> None:
        """In Phase 1, model is not loaded."""
        resp = client.get("/api/health")
        data = resp.json()
        assert data["model_loaded"] is False

    def test_health_qdrant_not_connected_yet(self, client: TestClient) -> None:
        """In Phase 1, Qdrant is not connected."""
        resp = client.get("/api/health")
        data = resp.json()
        assert data["qdrant_connected"] is False
