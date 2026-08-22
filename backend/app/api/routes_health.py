"""
Health and readiness check endpoints.
"""

from __future__ import annotations

import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.ml.image_encoder import ImageEncoder, get_image_encoder
from app.ml.text_encoder import TextEncoder, get_text_encoder
from app.repositories.knowledge_repository import (
    KnowledgeRepository,
    get_knowledge_repository,
)
from app.repositories.qdrant_repository import QdrantRepository, get_qdrant_repository

router = APIRouter(tags=["health"])

CACHE_TTL_SEC = 5.0
_health_cache: dict[str, Any] | None = None
_last_health_check_time: float = 0.0


class PublicConfigResponse(BaseModel):
    """Safe public configuration endpoint exposing non-sensitive runtime parameters."""

    app_version: str = Field(..., description="Application version")
    allowed_image_hosts: list[str] = Field(
        default_factory=list,
        description="Approved image CDN hostnames for client-side image rendering",
    )


class KnowledgeHealthInfo(BaseModel):
    """Health information for the Knowledge retrieval subsystem."""

    enabled: bool = Field(..., description="Whether the knowledge subsystem is enabled")
    model_loaded: bool = Field(..., description="Whether the BGE-M3 text encoder is loaded")
    connected: bool = Field(
        ..., description="Whether Qdrant Cloud knowledge collection is reachable"
    )
    collection_available: bool = Field(..., description="Whether knowledge collection exists")
    schema_valid: bool = Field(
        ..., description="Whether knowledge schema and keyword indexes are valid"
    )
    collection_name: str | None = Field(default=None, description="Knowledge collection name")
    vector_size: int | None = Field(default=None, description="Vector dimension (1024D)")
    distance: str | None = Field(default=None, description="Distance metric (Cosine)")
    points_count: int | None = Field(default=None, description="Total knowledge chunks count")
    keyword_indexes: list[str] | None = Field(
        default=None, description="Verified keyword payload indexes"
    )


class HealthResponse(BaseModel):
    """Response schema for the health endpoint."""

    status: str = Field(..., description="Service status: ok | degraded")
    model_loaded: bool = Field(..., description="Whether the image encoder model is loaded")
    qdrant_connected: bool = Field(..., description="Whether Qdrant Cloud is reachable")
    collection_available: bool = Field(
        ..., description="Whether the Qdrant gallery collection is available"
    )
    schema_valid: bool = Field(
        default=True,
        description="Whether the Qdrant gallery collection schema (768D Cosine) is valid",
    )
    collection_name: str | None = Field(default=None, description="Active gallery collection name")
    vector_size: int | None = Field(default=None, description="Gallery vector dimension")
    distance: str | None = Field(default=None, description="Gallery distance metric")
    points_count: int | None = Field(default=None, description="Gallery collection point count")
    knowledge: KnowledgeHealthInfo | None = Field(
        default=None, description="Knowledge subsystem health status"
    )
    version: str = Field(..., description="Application version")


@router.get("/health", response_model=HealthResponse)
async def health_check(
    encoder: Annotated[ImageEncoder, Depends(get_image_encoder)],
    repo: Annotated[QdrantRepository, Depends(get_qdrant_repository)],
    text_encoder: Annotated[TextEncoder, Depends(get_text_encoder)],
    knowledge_repo: Annotated[KnowledgeRepository, Depends(get_knowledge_repository)],
) -> HealthResponse:
    """
    Service health check.

    Returns cached health status (TTL 5s) to avoid unnecessary Qdrant load.
    Combines Gallery and Knowledge health inspection into a single unified health status.
    """
    global _health_cache, _last_health_check_time
    now = time.monotonic()

    if _health_cache is not None and (now - _last_health_check_time) < CACHE_TTL_SEC:
        return HealthResponse(**_health_cache)

    settings = get_settings()
    model_loaded = encoder.is_loaded

    # Gallery Qdrant health & schema check
    qdrant_connected, collection_available, schema_valid, schema_info = repo.get_health_status()

    # Knowledge Qdrant health & schema check if enabled
    knowledge_health: dict[str, Any] | None = None
    knowledge_healthy = True

    if settings.knowledge_enabled:
        k_model_loaded = text_encoder.is_loaded
        k_connected, k_col_avail, k_schema_valid, k_schema_info = knowledge_repo.get_health_status()
        knowledge_healthy = k_model_loaded and k_connected and k_col_avail and k_schema_valid

        if settings.is_production:
            knowledge_health = {
                "enabled": True,
                "model_loaded": k_model_loaded,
                "connected": k_connected,
                "collection_available": k_col_avail,
                "schema_valid": k_schema_valid,
                "collection_name": None,
                "vector_size": None,
                "distance": None,
                "points_count": None,
                "keyword_indexes": None,
            }
        else:
            knowledge_health = {
                "enabled": True,
                "model_loaded": k_model_loaded,
                "connected": k_connected,
                "collection_available": k_col_avail,
                "schema_valid": k_schema_valid,
                "collection_name": knowledge_repo.collection_name,
                "vector_size": k_schema_info.get("vector_size") if k_schema_info else None,
                "distance": k_schema_info.get("distance") if k_schema_info else None,
                "points_count": k_schema_info.get("points_count") if k_schema_info else None,
                "keyword_indexes": (
                    k_schema_info.get("keyword_indexes") if k_schema_info else None
                ),
            }

    gallery_healthy = model_loaded and qdrant_connected and collection_available and schema_valid
    is_fully_healthy = gallery_healthy and knowledge_healthy
    status_str = "ok" if is_fully_healthy else "degraded"

    if settings.is_production:
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
            "knowledge": knowledge_health,
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
            "knowledge": knowledge_health,
            "version": settings.app_version,
        }

    _health_cache = result_data
    _last_health_check_time = now

    return HealthResponse(**result_data)


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
    text_encoder: Annotated[TextEncoder, Depends(get_text_encoder)],
    knowledge_repo: Annotated[KnowledgeRepository, Depends(get_knowledge_repository)],
) -> JSONResponse:
    """
    Readiness probe endpoint for Kubernetes / Docker container health checks.
    Requires Gallery readiness (768D Cosine) AND Knowledge readiness (1024D Cosine + keyword indexes) if enabled.
    """
    settings = get_settings()
    gallery_ok, gallery_coll_ok, gallery_schema_ok, _ = repo.get_health_status()
    gallery_ready = encoder.is_loaded and gallery_ok and gallery_coll_ok and gallery_schema_ok

    knowledge_ready = True
    if settings.knowledge_enabled:
        k_connected, k_col_avail, k_schema_valid, _ = knowledge_repo.get_health_status()
        knowledge_ready = text_encoder.is_loaded and k_connected and k_col_avail and k_schema_valid

    if gallery_ready and knowledge_ready:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ready"},
        )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "not_ready"},
    )


@router.get("/public-config", response_model=PublicConfigResponse)
async def get_public_config() -> PublicConfigResponse:
    """
    Public configuration endpoint for the frontend client.
    Safely returns runtime public metadata such as allowed image CDN hosts and app version
    without disclosing any backend secrets, API keys, or internal cluster topologies.
    """
    settings = get_settings()
    return PublicConfigResponse(
        app_version=settings.app_version,
        allowed_image_hosts=settings.allowed_image_host_list,
    )
