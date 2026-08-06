"""
Health check endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Response schema for the health endpoint."""

    status: str = Field(..., description="Service status")
    model_loaded: bool = Field(..., description="Whether the classifier model is loaded")
    qdrant_connected: bool = Field(..., description="Whether Qdrant Cloud is reachable")
    version: str = Field(..., description="Application version")


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Service health check.

    Returns the service status, model availability, and Qdrant connectivity.
    Phase 5 will add real model and Qdrant checks.
    """
    settings = get_settings()
    return HealthResponse(
        status="ok",
        model_loaded=False,  # Updated in Phase 5 when model is loaded
        qdrant_connected=False,  # Updated in Phase 5 when Qdrant is connected
        version=settings.app_version,
    )
