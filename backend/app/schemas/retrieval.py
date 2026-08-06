"""
Pydantic schemas for image retrieval endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class QueryInfo(BaseModel):
    """Metadata about the query image."""

    filename: str = Field(..., description="Original filename of the query image")


class RetrievalResult(BaseModel):
    """A single retrieval result from vector database."""

    original_class: str = Field(..., description="Original Fruits-360 class name")
    canonical_class: str = Field(..., description="Canonical fruit class name (e.g. apple, papaya)")
    display_name: str = Field(
        ..., description="Human-friendly display name (e.g. Apple, Dragon Fruit)"
    )
    filename: str = Field(..., description="Filename of the matched image")
    relative_path: str = Field(..., description="Relative path of the matched image")
    original_split: str = Field(
        ..., description="Dataset split of the matched image (e.g. train, test)"
    )
    similarity: float = Field(
        ..., ge=-1.0, le=1.0, description="Cosine similarity score (-1.0 to 1.0)"
    )
    image_url: str | None = Field(
        default=None, description="Optional public URL to access the matched image"
    )


class RetrievalResponse(BaseModel):
    """Response body for POST /api/retrieve."""

    query: QueryInfo = Field(..., description="Query image info")
    results: list[RetrievalResult] = Field(..., description="Retrieved similar images")
    result_count: int = Field(..., description="Number of items returned in results")
    processing_time_ms: float = Field(..., description="Total processing time in milliseconds")
