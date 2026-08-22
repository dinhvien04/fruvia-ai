"""
Business logic service for semantic knowledge document retrieval.
"""

from __future__ import annotations

import time

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    KnowledgeDisabledError,
    KnowledgeValidationError,
)
from app.core.logging import get_logger
from app.ml.text_encoder import TextEncoder, get_text_encoder
from app.repositories.knowledge_repository import (
    KnowledgeRepository,
    get_knowledge_repository,
)
from app.schemas.knowledge import (
    KnowledgeDocumentResult,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSearchTiming,
    SpeciesKnowledgeResponse,
)
from app.utils.taxonomy import get_taxonomy_manager

logger = get_logger(__name__)


class KnowledgeService:
    """
    Service orchestrating text validation, BGE-M3 dense encoding, Qdrant grouped semantic search,
    taxonomy resolution, and document provenance normalization.
    """

    def __init__(
        self,
        text_encoder: TextEncoder | None = None,
        knowledge_repo: KnowledgeRepository | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.encoder = text_encoder or get_text_encoder()
        self.repo = knowledge_repo or get_knowledge_repository()
        self.taxonomy = get_taxonomy_manager()

    def _ensure_enabled(self) -> None:
        """Check if the knowledge retrieval subsystem is enabled in settings."""
        if not self.settings.knowledge_enabled:
            raise KnowledgeDisabledError(
                message="The knowledge retrieval service is currently disabled.",
                detail="KNOWLEDGE_ENABLED is false in configuration.",
            )

    def search_knowledge(self, request: KnowledgeSearchRequest) -> KnowledgeSearchResponse:
        """
        Execute semantic knowledge search for a natural language text query.

        Parameters
        ----------
        request : KnowledgeSearchRequest
            Search request containing query string, canonical_class, optional document_type, and limit.

        Returns
        -------
        KnowledgeSearchResponse
            Retrieved unique knowledge documents with scores, provenance, and performance timing.
        """
        self._ensure_enabled()
        t_start = time.perf_counter()

        # Validate input query constraints
        clean_query = request.query.strip()
        if not clean_query:
            raise KnowledgeValidationError(
                message="Query string cannot be empty or whitespace.",
                detail="Received empty query in KnowledgeSearchRequest.",
            )

        if len(clean_query) > self.settings.knowledge_max_query_chars:
            raise KnowledgeValidationError(
                message=f"Query exceeds maximum character limit of {self.settings.knowledge_max_query_chars}.",
                detail=f"Query length: {len(clean_query)}",
            )

        # Handle limit with backwards compatibility for top_k alias
        requested_limit = request.limit
        if request.top_k is not None:
            requested_limit = request.top_k
        limit = min(requested_limit, self.settings.knowledge_max_top_k)

        # Validate required canonical_class filter
        canonical_class = request.canonical_class.strip().lower()
        if not canonical_class:
            raise KnowledgeValidationError(
                message="canonical_class is required for knowledge search.",
                detail="Received empty canonical_class in KnowledgeSearchRequest.",
            )

        tax_item = self.taxonomy.get_item(canonical_class)
        if not tax_item:
            logger.debug(
                "Search filtered on uncataloged canonical_class '%s' (not in taxonomy.yaml).",
                canonical_class,
            )

        doc_type = request.document_type.strip().lower() if request.document_type else None

        logger.info(
            "Executing knowledge search for query='%s' (chars=%d, limit=%d, canonical_class=%s, doc_type=%s)...",
            clean_query[:50],
            len(clean_query),
            limit,
            canonical_class,
            doc_type,
        )

        # 1. Generate 1024D dense embedding via BGE-M3
        t_emb_start = time.perf_counter()
        query_vector = self.encoder.encode_text(clean_query)
        embedding_ms = round((time.perf_counter() - t_emb_start) * 1000, 2)

        # 2. Query Qdrant Cloud knowledge collection via native grouped retrieval
        t_search_start = time.perf_counter()
        raw_hits = self.repo.query_knowledge_grouped(
            vector=query_vector,
            canonical_class=canonical_class,
            document_type=doc_type,
            limit=limit,
        )
        vector_search_ms = round((time.perf_counter() - t_search_start) * 1000, 2)

        # 3. Normalize document results with taxonomy and metadata
        results: list[KnowledgeDocumentResult] = []
        for hit in raw_hits:
            payload = hit.get("payload", {})
            score = float(hit.get("score", 0.0))
            hit_id = hit.get("id")
            doc_id = str(hit.get("document_id") or payload.get("document_id") or "")

            doc_canon = str(payload.get("canonical_class") or canonical_class).strip().lower()
            hit_tax_item = self.taxonomy.get_item(doc_canon) or tax_item

            display_en = (
                hit_tax_item.name_en
                if hit_tax_item
                else (payload.get("display_name") or doc_canon.capitalize())
            )
            display_vi = hit_tax_item.name_vi if hit_tax_item else payload.get("display_name_vi")
            category = (
                hit_tax_item.category if hit_tax_item else (payload.get("category") or "fruit")
            )

            raw_metadata = payload.get("metadata") or {}
            if not isinstance(raw_metadata, dict):
                raw_metadata = {}

            # Extract specific structured properties if present in payload
            nutrients = (
                payload.get("nutrients") if isinstance(payload.get("nutrients"), dict) else None
            )
            taxonomy_data = (
                payload.get("taxonomy") if isinstance(payload.get("taxonomy"), dict) else None
            )
            scientific_name = payload.get("scientific_name")
            if (
                not scientific_name
                and hit_tax_item
                and getattr(hit_tax_item, "scientific_name", None)
            ):
                scientific_name = getattr(hit_tax_item, "scientific_name", None)

            source_dataset = payload.get("source_dataset")
            source_url = payload.get("source_url")
            language = payload.get("language")

            doc_res = KnowledgeDocumentResult(
                id=hit_id,
                document_id=doc_id,
                score=round(score, 4),
                canonical_class=doc_canon,
                display_name=display_en,
                display_name_vi=display_vi,
                category=category,
                document_type=str(payload.get("document_type") or "general"),
                source=str(payload.get("source") or payload.get("source_dataset") or "unknown"),
                source_dataset=source_dataset,
                language=language,
                title=str(payload.get("title") or payload.get("name") or "Untitled Document"),
                source_url=source_url,
                text=str(payload.get("text") or payload.get("content") or ""),
                scientific_name=scientific_name,
                nutrients=nutrients,
                taxonomy=taxonomy_data,
                metadata=raw_metadata,
            )
            results.append(doc_res)

        total_ms = round((time.perf_counter() - t_start) * 1000, 2)
        timing = KnowledgeSearchTiming(
            embedding_ms=embedding_ms,
            vector_search_ms=vector_search_ms,
            total_ms=total_ms,
        )

        logger.info(
            "Knowledge search completed in %.2f ms (emb: %.1fms, search: %.1fms). Found %d unique documents.",
            total_ms,
            embedding_ms,
            vector_search_ms,
            len(results),
        )

        return KnowledgeSearchResponse(
            query=clean_query,
            canonical_class=canonical_class,
            document_type=doc_type,
            results=results,
            result_count=len(results),
            processing_time_ms=total_ms,
            timing=timing,
        )

    def get_species_knowledge(
        self,
        canonical_class: str,
        limit: int = 10,
    ) -> SpeciesKnowledgeResponse:
        """
        Convenience method to retrieve knowledge documents and nutrition facts
        for a specific canonical species identifier.

        Parameters
        ----------
        canonical_class : str
            Canonical biological species identifier.
        limit : int
            Maximum number of distinct documents to return.

        Returns
        -------
        SpeciesKnowledgeResponse
            Taxonomy details and associated unique knowledge documents.
        """
        self._ensure_enabled()
        t_start = time.perf_counter()

        canon = canonical_class.strip().lower()
        if not canon:
            raise KnowledgeValidationError(
                message="canonical_class cannot be empty.",
                detail="Received empty canonical_class in get_species_knowledge.",
            )

        tax_item = self.taxonomy.get_item(canon)

        display_en = tax_item.name_en if tax_item else canon.capitalize()
        display_vi = tax_item.name_vi if tax_item else None
        category = tax_item.category if tax_item else "fruit"

        # Construct a representative query from species names for semantic retrieval
        query_text = (
            f"{display_en} {display_vi or ''} nutrition botanical facts characteristics".strip()
        )
        search_req = KnowledgeSearchRequest(
            query=query_text,
            canonical_class=canon,
            limit=min(limit, self.settings.knowledge_max_top_k),
        )

        search_resp = self.search_knowledge(search_req)
        total_ms = round((time.perf_counter() - t_start) * 1000, 2)

        return SpeciesKnowledgeResponse(
            canonical_class=canon,
            display_name=display_en,
            display_name_vi=display_vi,
            category=category,
            documents=search_resp.results,
            document_count=len(search_resp.results),
            processing_time_ms=total_ms,
        )


_service_instance: KnowledgeService | None = None


def get_knowledge_service() -> KnowledgeService:
    """Return KnowledgeService instance."""
    return KnowledgeService()
