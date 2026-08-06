"""
Health and readiness check endpoints.
"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.ml.image_encoder import ImageEncoder, get_image_encoder
from app.repositories.qdrant_repository import QdrantRepository, get_qdrant_repository

router = APIRouter(tags=["health"])

CACHE_TTL_SEC = 5.0
_health_cache: dict[str, float | bool | str] | None = None
_last_health_check_time: float = 0.0


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

    Returns cached health status (TTL 5s) to avoid unnecessary Qdrant load.
    Combines Qdrant connection and collection availability check into a single call.
    """
    global _health_cache, _last_health_check_time
    now = time.monotonic()

    if _health_cache is not None and (now - _last_health_check_time) < CACHE_TTL_SEC:
        return HealthResponse(**_health_cache)  # type: ignore[arg-type]

    settings = get_settings()
    model_loaded = encoder.is_loaded

    # Single Qdrant health check call
    qdrant_connected, collection_available = repo.get_health_status()

    is_fully_healthy = model_loaded and qdrant_connected and collection_available
    status = "ok" if is_fully_healthy else "degraded"

    result_data = {
        "status": status,
        "model_loaded": model_loaded,
        "qdrant_connected": qdrant_connected,
        "collection_available": collection_available,
        "version": settings.app_version,
    }

    _health_cache = result_data  # type: ignore[assignment]
    _last_health_check_time = now

    return HealthResponse(**result_data)  # type: ignore[arg-type]


@router.get("/ready")
async def readiness_check(
    encoder: Annotated[ImageEncoder, Depends(get_image_encoder)],
    repo: Annotated[QdrantRepository, Depends(get_qdrant_repository)],
) -> dict[str, str]:
    """Readiness probe endpoint for Kubernetes / Docker container health checks."""
    qdrant_ok, coll_ok = repo.get_health_status()
    if encoder.is_loaded and qdrant_ok and coll_ok:
        return {"status": "ready"}
    return {"status": "not_ready"}
