"""
Health and readiness check endpoints.
"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
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
    schema_valid: bool = Field(
        default=True, description="Whether the Qdrant collection schema (768D Cosine) is valid"
    )
    collection_name: str | None = Field(default=None, description="Active gallery collection name")
    vector_size: int | None = Field(default=None, description="Vector dimension")
    distance: str | None = Field(default=None, description="Distance metric")
    points_count: int | None = Field(default=None, description="Collection point count")
    version: str = Field(..., description="Application version")


@router.get("/health", response_model=HealthResponse)
async def health_check(
    encoder: Annotated[ImageEncoder, Depends(get_image_encoder)],
    repo: Annotated[QdrantRepository, Depends(get_qdrant_repository)],
) -> HealthResponse:
    """
    Service health check.

    Returns cached health status (TTL 5s) to avoid unnecessary Qdrant load.
    Combines Qdrant connection, collection availability, and schema inspection into a single call.
    """
    global _health_cache, _last_health_check_time
    now = time.monotonic()

    if _health_cache is not None and (now - _last_health_check_time) < CACHE_TTL_SEC:
        return HealthResponse(**_health_cache)  # type: ignore[arg-type]

    settings = get_settings()
    model_loaded = encoder.is_loaded

    # Single Qdrant health & schema check call
    qdrant_connected, collection_available, schema_valid, schema_info = repo.get_health_status()

    is_fully_healthy = model_loaded and qdrant_connected and collection_available and schema_valid
    status_str = "ok" if is_fully_healthy else "degraded"

    if settings.is_production:
        # Minimal information disclosure in production
        result_data = {
            "status": status_str,
            "model_loaded": model_loaded,
            "qdrant_connected": qdrant_connected,
            "collection_available": collection_available,
            "schema_valid": schema_valid,
            "collection_name": None,
            "vector_size": None,
            "distance": None,
            "points_count": None,
            "version": settings.app_version,
        }
    else:
        result_data = {
            "status": status_str,
            "model_loaded": model_loaded,
            "qdrant_connected": qdrant_connected,
            "collection_available": collection_available,
            "schema_valid": schema_valid,
            "collection_name": repo.collection_name,
            "vector_size": schema_info.get("vector_size") if schema_info else None,
            "distance": schema_info.get("distance") if schema_info else None,
            "points_count": schema_info.get("points_count") if schema_info else None,
            "version": settings.app_version,
        }

    _health_cache = result_data  # type: ignore[assignment]
    _last_health_check_time = now

    return HealthResponse(**result_data)  # type: ignore[arg-type]


@router.get("/live")
async def liveness_check() -> JSONResponse:
    """
    Liveness probe endpoint for Kubernetes / process monitors.
    Confirms the application event loop and process are alive without querying external backends.
    """
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "live"},
    )


@router.get("/ready")
async def readiness_check(
    encoder: Annotated[ImageEncoder, Depends(get_image_encoder)],
    repo: Annotated[QdrantRepository, Depends(get_qdrant_repository)],
) -> JSONResponse:
    """
    Readiness probe endpoint for Kubernetes / Docker container health checks.
    Requires model loaded + Qdrant reachable + collection available + 768D Cosine schema valid.
    """
    qdrant_ok, coll_ok, schema_ok, _ = repo.get_health_status()
    if encoder.is_loaded and qdrant_ok and coll_ok and schema_ok:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ready"},
        )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "not_ready"},
    )
