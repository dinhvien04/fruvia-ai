"""
Health check endpoint.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.ml.image_encoder import ImageEncoder, get_image_encoder
from app.repositories.qdrant_repository import QdrantRepository, get_qdrant_repository

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Response schema for the health endpoint."""

    status: str = Field(..., description="Service status: ok | degraded")
    model_loaded: bool = Field(..., description="Whether the image encoder model is loaded")
    qdrant_connected: bool = Field(..., description="Whether Qdrant Cloud is reachable")
    collection_available: bool = Field(
        ..., description="Whether the Qdrant collection is available"
    )
    version: str = Field(..., description="Application version")


@router.get("/health", response_model=HealthResponse)
async def health_check(
    encoder: Annotated[ImageEncoder, Depends(get_image_encoder)],
    repo: Annotated[QdrantRepository, Depends(get_qdrant_repository)],
) -> HealthResponse:
    """
    Service health check.

    Returns service status, model availability, and Qdrant connectivity.
    """
    settings = get_settings()

    model_loaded = encoder.is_loaded
    qdrant_connected = repo.is_connected()
    collection_available = repo.is_collection_available() if qdrant_connected else False

    is_fully_healthy = model_loaded and qdrant_connected and collection_available
    status = "ok" if is_fully_healthy else "degraded"

    return HealthResponse(
        status=status,
        model_loaded=model_loaded,
        qdrant_connected=qdrant_connected,
        collection_available=collection_available,
        version=settings.app_version,
    )
