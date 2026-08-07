"""
Pydantic schemas for image retrieval endpoints.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class QueryInfo(BaseModel):
    """Metadata about the query image."""

    filename: str = Field(..., description="Original filename of the query image")


class RetrievalResult(BaseModel):
    """A single retrieval result from vector database."""

    original_class: str = Field(
        ..., description="Original raw class label from dataset (e.g. apple_red_2)"
    )
    canonical_class: str = Field(
        ..., description="Canonical species class name (e.g. apple, durian)"
    )
    display_name: str = Field(
        ..., description="Human-friendly English display name (e.g. Apple, Durian)"
    )
    display_name_vi: str | None = Field(
        default=None, description="Optional Vietnamese display name (e.g. Táo, Sầu riêng)"
    )
    category: str = Field(
        default="fruit",
        description="Category classification: fruit | vegetable | nut | seed | other",
    )
    dataset_name: str = Field(
        default="fruits360_original",
        description="Source dataset name (e.g. fruits262_full_original_v7)",
    )
    dataset_version: str | None = Field(default=None, description="Source dataset version (e.g. 7)")
    filename: str = Field(..., description="Filename of the matched image")
    relative_path: str = Field(..., description="Relative path of the matched image")
    original_split: str = Field(
        ..., description="Dataset split of matched image (e.g. train, test, gallery)"
    )
    similarity: float = Field(
        ..., ge=-1.0, le=1.0, description="Cosine similarity score (-1.0 to 1.0)"
    )
    image_url: str | None = Field(
        default=None, description="Optional public URL/R2 thumbnail to access matched image"
    )
    hit_count: int | None = Field(
        default=None, description="Number of candidate matches for this class in class search mode"
    )


class RetrievalResponse(BaseModel):
    """Response body for POST /api/retrieve."""

    query: QueryInfo = Field(..., description="Query image info")
    mode: Literal["image", "class"] = Field(
        default="image",
        description="Retrieval mode: 'image' (top-K images) or 'class' (grouped by class)",
    )
    category: str = Field(
        default="all", description="Category filter applied (all, fruit, vegetable, nut, seed)"
    )
    results: list[RetrievalResult] = Field(..., description="Retrieved similar items")
    result_count: int = Field(..., description="Number of items returned in results")
    processing_time_ms: float = Field(..., description="Total processing time in milliseconds")
