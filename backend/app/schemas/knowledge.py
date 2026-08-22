"""
Pydantic schemas for the Fruvia Knowledge retrieval subsystem.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class KnowledgeSearchRequest(BaseModel):
    """Request body for POST /api/knowledge/search."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Natural language query or question about fruit botanical, encyclopedic, or nutritional info",
    )
    canonical_class: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Required filter by canonical species identifier (e.g. 'apple', 'durian')",
    )
    document_type: str | None = Field(
        default=None,
        max_length=100,
        description="Optional filter by document type (e.g. 'nutrition', 'encyclopedia', 'taxonomy_scientific', 'botanical')",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Number of distinct knowledge documents to retrieve",
    )
    top_k: int | None = Field(
        default=None,
        ge=1,
        le=50,
        description="Deprecated alias for limit (preserved for backwards compatibility)",
    )

    @field_validator("document_type", mode="before")
    @classmethod
    def normalize_document_type(cls, v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip().lower()
            return s if s else None
        return str(v).strip().lower()


class KnowledgeDocumentResult(BaseModel):
    """A single retrieved knowledge document or passage with full provenance."""

    id: str | int | None = Field(default=None, description="Qdrant point identifier")
    document_id: str = Field(
        ...,
        description="Canonical document identifier grouping multiple chunk vectors",
    )
    score: float = Field(
        ...,
        ge=-1.0,
        le=1.0,
        description="Cosine similarity score between query and document embedding (-1.0 to 1.0)",
    )
    canonical_class: str = Field(
        ...,
        description="Canonical biological species identifier associated with this document",
    )
    display_name: str | None = Field(
        default=None, description="English display name resolved from taxonomy"
    )
    display_name_vi: str | None = Field(
        default=None, description="Vietnamese display name resolved from taxonomy"
    )
    category: str = Field(
        default="other",
        description="Biological/culinary category: fruit | vegetable | nut | seed | other",
    )
    document_type: str = Field(
        default="general",
        description="Type of knowledge document: nutrition | encyclopedia | taxonomy_scientific | botanical | general",
    )
    source: str = Field(
        default="unknown",
        description="Provenance source identifier (e.g. 'wikipedia', 'usda_fooddata_central')",
    )
    source_dataset: str | None = Field(
        default=None,
        description="Source dataset identifier if applicable",
    )
    language: str | None = Field(
        default=None,
        description="Language code of document (e.g. 'vi', 'en')",
    )
    title: str = Field(..., description="Document or section title")
    source_url: str | None = Field(
        default=None,
        description="Authoritative source citation URL",
    )
    text: str = Field(..., description="Full text snippet or passage")
    scientific_name: str | None = Field(
        default=None,
        description="Scientific / botanical Latin name when present",
    )
    nutrients: dict[str, Any] | None = Field(
        default=None,
        description="Nutrient profile dictionary when present",
    )
    taxonomy: dict[str, Any] | None = Field(
        default=None,
        description="Detailed biological taxonomy structure when present",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional structured metadata or raw attributes",
    )


class KnowledgeSearchTiming(BaseModel):
    """Execution timing breakdown in milliseconds for knowledge search."""

    embedding_ms: float = Field(..., description="BGE-M3 text encoding duration in ms")
    vector_search_ms: float = Field(..., description="Qdrant grouped vector search duration in ms")
    total_ms: float = Field(..., description="Total end-to-end processing duration in ms")


class KnowledgeSearchResponse(BaseModel):
    """Response body for POST /api/knowledge/search."""

    query: str = Field(..., description="The original query text")
    canonical_class: str = Field(..., description="Canonical class filter applied")
    document_type: str | None = Field(default=None, description="Document type filter applied")
    results: list[KnowledgeDocumentResult] = Field(
        ..., description="List of matching unique knowledge documents with provenance"
    )
    result_count: int = Field(..., description="Number of unique documents returned")
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
        ..., description="Total count of unique knowledge documents for this species"
    )
    processing_time_ms: float = Field(..., description="Total query execution time in milliseconds")
