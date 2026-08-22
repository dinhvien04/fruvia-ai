"""
Knowledge retrieval API route handlers.

Provides semantic search endpoints for botanical and nutritional knowledge
grounded in Qdrant Cloud BGE-M3 embeddings.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from starlette.concurrency import run_in_threadpool

from app.core.exceptions import KnowledgeValidationError
from app.core.rate_limit import get_concurrency_limiter
from app.schemas.knowledge import (
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    SpeciesKnowledgeResponse,
)
from app.services.knowledge_service import KnowledgeService, get_knowledge_service

router = APIRouter(tags=["knowledge"])


@router.post("/knowledge/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    request: KnowledgeSearchRequest,
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)],
) -> KnowledgeSearchResponse:
    """
    Perform semantic vector search on botanical and nutritional knowledge documents.

    Encodes the text query using BGE-M3 (1024D) and retrieves top matching documents
    from Qdrant Cloud. Preserves full document provenance, source citations,
    and nutritional metadata without generative hallucination.
    """
    clean_query = request.query.strip()
    if not clean_query:
        raise KnowledgeValidationError(
            message="Query cannot be empty.",
            detail="query string is empty or whitespace only.",
        )

    limiter = get_concurrency_limiter()
    return await limiter.run(
        run_in_threadpool,
        service.search_knowledge,
        request=request,
    )


@router.get("/species/{canonical_class}/knowledge", response_model=SpeciesKnowledgeResponse)
async def get_species_knowledge(
    canonical_class: str,
    limit: Annotated[int, Query(ge=1, le=50, description="Max documents to retrieve")] = 5,
    service: Annotated[KnowledgeService, Depends(get_knowledge_service)] = None,  # type: ignore[assignment]
) -> SpeciesKnowledgeResponse:
    """
    Retrieve knowledge documents and nutritional profile for a specific canonical species.

    Convenience endpoint connecting the canonical species taxonomy to the BGE-M3 knowledge repository.
    """
    canon = canonical_class.strip().lower()
    if not canon:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="canonical_class cannot be empty.",
        )

    limiter = get_concurrency_limiter()
    return await limiter.run(
        run_in_threadpool,
        service.get_species_knowledge,
        canonical_class=canon,
        limit=limit,
    )
