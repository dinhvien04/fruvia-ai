"""
Pydantic schemas for image retrieval endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class QueryInfo(BaseModel):
    """Metadata about the query image."""

    filename: str = Field(..., description="Original filename of the query image")


class RetrievalResult(BaseModel):
    """A single retrieval result from Qdrant."""

    image_id: str = Field(..., description="Unique image identifier")
    fruit_class: str = Field(..., description="Fruit class label")
    image_url: str | None = Field(None, description="URL or path to the result image")
    similarity: float = Field(..., ge=0.0, le=1.0, description="Cosine similarity score")
    original_class: str | None = Field(None, description="Original Fruits-360 class name")


class RetrievalResponse(BaseModel):
    """Response body for POST /api/retrieve."""

    query: QueryInfo = Field(..., description="Query image info")
    results: list[RetrievalResult] = Field(..., description="Retrieved similar images")
    top_k: int = Field(..., description="Number of results requested")
    processing_time_ms: float = Field(..., description="Total processing time in milliseconds")
