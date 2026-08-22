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
    Service orchestrating text validation, BGE-M3 dense encoding, Qdrant semantic search,
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
            Search request containing query string, top_k, and optional filters.

        Returns
        -------
        KnowledgeSearchResponse
            Retrieved knowledge documents with scores, provenance, and performance timing.
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

        top_k = min(request.top_k, self.settings.knowledge_max_top_k)

        # Validate canonical_class filter if supplied
        canonical_class = (
            request.canonical_class.strip().lower() if request.canonical_class else None
        )
        if canonical_class:
            tax_item = self.taxonomy.get_item(canonical_class)
            if not tax_item:
                logger.debug(
                    "Search filtered on uncataloged canonical_class '%s' (not in taxonomy.yaml).",
                    canonical_class,
                )

        doc_type = request.document_type.strip().lower() if request.document_type else None

        logger.info(
            "Executing knowledge search for query='%s' (chars=%d, top_k=%d, canonical_class=%s, doc_type=%s)...",
            clean_query[:50],
            len(clean_query),
            top_k,
            canonical_class,
            doc_type,
        )

        # 1. Generate 1024D dense embedding via BGE-M3
        t_emb_start = time.perf_counter()
        query_vector = self.encoder.encode_text(clean_query)
        embedding_ms = round((time.perf_counter() - t_emb_start) * 1000, 2)

        # 2. Query Qdrant Cloud knowledge collection
        t_search_start = time.perf_counter()
        raw_hits = self.repo.query_knowledge(
            vector=query_vector,
            top_k=top_k,
            canonical_class=canonical_class,
            document_type=doc_type,
        )
        vector_search_ms = round((time.perf_counter() - t_search_start) * 1000, 2)

        # 3. Normalize document results with taxonomy and metadata
        results: list[KnowledgeDocumentResult] = []
        for hit in raw_hits:
            payload = hit.get("payload", {})
            score = hit.get("score", 0.0)
            hit_id = hit.get("id")

            doc_canon = str(payload.get("canonical_class") or "unknown").strip().lower()
            tax_item = self.taxonomy.get_item(doc_canon)

            display_en = tax_item.name_en if tax_item else payload.get("display_name")
            display_vi = tax_item.name_vi if tax_item else payload.get("display_name_vi")
            category = tax_item.category if tax_item else (payload.get("category") or "fruit")

            # Extract nutrient dictionary or other structured metadata if present
            raw_metadata = payload.get("metadata") or {}
            if not isinstance(raw_metadata, dict):
                raw_metadata = {}

            # Incorporate top-level nutrients or nutritional properties if available
            if "nutrients" in payload and isinstance(payload["nutrients"], dict):
                raw_metadata["nutrients"] = payload["nutrients"]
            if "usda_ndb_number" in payload:
                raw_metadata["usda_ndb_number"] = payload["usda_ndb_number"]

            doc_res = KnowledgeDocumentResult(
                id=hit_id,
                title=str(payload.get("title") or payload.get("name") or "Untitled Document"),
                text=str(payload.get("text") or payload.get("content") or ""),
                source=str(payload.get("source") or payload.get("source_dataset") or "unknown"),
                canonical_class=doc_canon,
                display_name=display_en,
                display_name_vi=display_vi,
                category=category,
                document_type=str(payload.get("document_type") or "general"),
                similarity=round(score, 4),
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
            "Knowledge search completed in %.2f ms (emb: %.1fms, search: %.1fms). Found %d documents.",
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
            Maximum number of documents to return.

        Returns
        -------
        SpeciesKnowledgeResponse
            Taxonomy details and associated knowledge documents.
        """
        self._ensure_enabled()
        t_start = time.perf_counter()

        canon = canonical_class.strip().lower()
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
            top_k=min(limit, self.settings.knowledge_max_top_k),
            canonical_class=canon,
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
