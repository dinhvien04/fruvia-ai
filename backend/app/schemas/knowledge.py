"""
Pydantic schemas for the Fruvia Knowledge retrieval subsystem.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class KnowledgeSearchRequest(BaseModel):
    """Request body for POST /api/knowledge/search."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural language query or question about fruit botanical or nutritional info",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of knowledge document passages to retrieve",
    )
    canonical_class: str | None = Field(
        default=None,
        description="Optional filter by canonical species identifier (e.g. 'apple', 'durian')",
    )
    document_type: str | None = Field(
        default=None,
        description="Optional filter by document type (e.g. 'nutrition', 'botanical', 'general')",
    )


class KnowledgeDocumentResult(BaseModel):
    """A single retrieved knowledge document or passage with full provenance."""

    id: str | int | None = Field(default=None, description="Qdrant point identifier")
    title: str = Field(..., description="Document or section title")
    text: str = Field(..., description="Full text snippet or passage")
    source: str = Field(
        default="unknown",
        description="Provenance source identifier (e.g. 'usda_fooddata_central', 'wikipedia', 'botanical_guide')",
    )
    canonical_class: str = Field(
        default="unknown",
        description="Canonical biological species identifier associated with this document",
    )
    display_name: str | None = Field(
        default=None, description="English display name resolved from taxonomy"
    )
    display_name_vi: str | None = Field(
        default=None, description="Vietnamese display name resolved from taxonomy"
    )
    category: str = Field(
        default="fruit",
        description="Biological/culinary category: fruit | vegetable | nut | seed | other",
    )
    document_type: str = Field(
        default="general",
        description="Type of knowledge document: nutrition | botanical | culinary | general",
    )
    similarity: float = Field(
        ...,
        ge=-1.0,
        le=1.0,
        description="Cosine similarity score between query and document embedding (-1.0 to 1.0)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional structured metadata, raw USDA nutrient key-values, or citations",
    )


class KnowledgeSearchTiming(BaseModel):
    """Execution timing breakdown in milliseconds for knowledge search."""

    embedding_ms: float = Field(..., description="BGE-M3 text encoding duration in ms")
    vector_search_ms: float = Field(..., description="Qdrant vector search duration in ms")
    total_ms: float = Field(..., description="Total end-to-end processing duration in ms")


class KnowledgeSearchResponse(BaseModel):
    """Response body for POST /api/knowledge/search."""

    query: str = Field(..., description="The original query text")
    canonical_class: str | None = Field(default=None, description="Canonical class filter applied")
    document_type: str | None = Field(default=None, description="Document type filter applied")
    results: list[KnowledgeDocumentResult] = Field(
        ..., description="List of matching knowledge documents with provenance"
    )
    result_count: int = Field(..., description="Number of results returned")
    processing_time_ms: float = Field(..., description="Total processing time in milliseconds")
    timing: KnowledgeSearchTiming | None = Field(
        default=None, description="Detailed stage-by-stage timing"
    )


class SpeciesKnowledgeResponse(BaseModel):
    """Response body for GET /api/species/{canonical_class}/knowledge."""

    canonical_class: str = Field(..., description="Canonical species identifier")
    display_name: str = Field(..., description="English common name")
    display_name_vi: str | None = Field(default=None, description="Vietnamese common name")
    category: str = Field(
        ..., description="Species category: fruit | vegetable | nut | seed | other"
    )
    documents: list[KnowledgeDocumentResult] = Field(
        ..., description="Associated knowledge documents and nutritional profiles"
    )
    document_count: int = Field(
        ..., description="Total count of knowledge documents for this species"
    )
    processing_time_ms: float = Field(..., description="Total query execution time in milliseconds")
