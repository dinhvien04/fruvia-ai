"""
Business logic service for semantic knowledge document retrieval.
"""

from __future__ import annotations

import time
from typing import Any

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    KnowledgeDisabledError,
    KnowledgeSpeciesNotFoundError,
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
from app.utils.taxonomy import TaxonomyManager, get_taxonomy_manager

logger = get_logger(__name__)


class KnowledgeService:
    """
    Service orchestrating text validation, taxonomy verification, BGE-M3 dense encoding,
    Qdrant grouped semantic search, and document provenance normalization.
    """

    def __init__(
        self,
        text_encoder: TextEncoder | None = None,
        knowledge_repo: KnowledgeRepository | None = None,
        taxonomy_manager: TaxonomyManager | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.encoder = text_encoder or get_text_encoder()
        self.repo = knowledge_repo or get_knowledge_repository()
        self.taxonomy = taxonomy_manager or get_taxonomy_manager()

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

        Raises
        ------
        KnowledgeSpeciesNotFoundError
            If canonical_class does not exist in the taxonomy.
        KnowledgeValidationError
            If query or limit exceeds configured settings constraints.
        """
        self._ensure_enabled()
        t_start = time.perf_counter()

        # 1. Validate required canonical_class and verify against taxonomy FIRST
        # Unknown class MUST fail fast before encoder or Qdrant are invoked.
        if not request.canonical_class:
            raise KnowledgeValidationError(
                message="canonical_class is required for knowledge search.",
                detail="canonical_class was empty or not supplied.",
            )

        canonical_class = request.canonical_class.strip().lower()
        if not canonical_class:
            raise KnowledgeValidationError(
                message="canonical_class cannot be empty or whitespace.",
                detail="Received empty canonical_class in KnowledgeSearchRequest.",
            )

        tax_item = self.taxonomy.get_item(canonical_class)
        if not tax_item:
            logger.warning(
                "Knowledge search requested for unknown canonical_class '%s'", canonical_class
            )
            raise KnowledgeSpeciesNotFoundError(
                message=f"Species '{canonical_class}' not found in taxonomy.",
                detail=f"canonical_class '{canonical_class}' does not exist in taxonomy.yaml",
            )

        # 2. Validate input query constraints against settings
        clean_query = request.query.strip()
        if not clean_query:
            raise KnowledgeValidationError(
                message="Query string cannot be empty or whitespace.",
                detail="Received empty query in KnowledgeSearchRequest.",
            )

        if len(clean_query) > self.settings.knowledge_max_query_chars:
            raise KnowledgeValidationError(
                message=f"Query exceeds maximum character limit of {self.settings.knowledge_max_query_chars}.",
                detail=f"Query length: {len(clean_query)} > max: {self.settings.knowledge_max_query_chars}",
            )

        # 3. Validate limit against settings
        requested_limit = request.limit
        if request.top_k is not None:
            requested_limit = request.top_k

        if requested_limit > self.settings.knowledge_max_top_k:
            raise KnowledgeValidationError(
                message=f"limit {requested_limit} exceeds maximum allowed {self.settings.knowledge_max_top_k}.",
                detail=f"Requested limit: {requested_limit}, max_top_k: {self.settings.knowledge_max_top_k}",
            )
        limit = requested_limit

        # 4. Normalize document_type filter
        doc_type = request.document_type.strip().lower() if request.document_type else None

        logger.info(
            "Executing knowledge search for query='%s' (chars=%d, limit=%d, canonical_class=%s, doc_type=%s)...",
            clean_query[:50],
            len(clean_query),
            limit,
            canonical_class,
            doc_type,
        )

        # 5. Generate 1024D dense embedding via BGE-M3
        t_emb_start = time.perf_counter()
        query_vector = self.encoder.encode_text(clean_query)
        embedding_ms = round((time.perf_counter() - t_emb_start) * 1000, 2)

        # 6. Query Qdrant Cloud knowledge collection via native grouped retrieval
        t_search_start = time.perf_counter()
        raw_hits = self.repo.query_knowledge_grouped(
            vector=query_vector,
            canonical_class=canonical_class,
            document_type=doc_type,
            limit=limit,
        )
        vector_search_ms = round((time.perf_counter() - t_search_start) * 1000, 2)

        # 7. Normalize document results with taxonomy and metadata
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
                else (payload.get("display_name") or doc_canon.replace("_", " ").title())
            )
            display_vi = hit_tax_item.name_vi if hit_tax_item else payload.get("display_name_vi")

            # Category resolution: taxonomy -> payload category -> "other" (never default to "fruit")
            if hit_tax_item and hit_tax_item.category:
                category = hit_tax_item.category
            elif payload.get("category"):
                category = str(payload.get("category"))
            else:
                category = "other"

            # Safely parse metadata as dict
            raw_metadata = payload.get("metadata")
            metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}

            # Extract nutrients: top-level payload["nutrients"] -> metadata["nutrients"] -> None
            nutrients: dict[str, Any] | None = None
            if isinstance(payload.get("nutrients"), dict):
                nutrients = payload.get("nutrients")
            elif isinstance(metadata.get("nutrients"), dict):
                nutrients = metadata.get("nutrients")

            taxonomy_data = (
                payload.get("taxonomy") if isinstance(payload.get("taxonomy"), dict) else None
            )
            scientific_name = payload.get("scientific_name")
            if not scientific_name and hit_tax_item:
                tax_sci = getattr(hit_tax_item, "scientific_name", None)
                if isinstance(tax_sci, str) and tax_sci.strip():
                    scientific_name = tax_sci.strip()
            if scientific_name and not isinstance(scientific_name, str):
                scientific_name = str(scientific_name)

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
                metadata=metadata,
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

        Raises
        ------
        KnowledgeSpeciesNotFoundError
            If canonical_class does not exist in the taxonomy.
        KnowledgeValidationError
            If limit or canonical_class parameters fail validation.
        """
        self._ensure_enabled()
        t_start = time.perf_counter()

        if not canonical_class:
            raise KnowledgeValidationError(
                message="canonical_class cannot be empty.",
                detail="Received empty canonical_class in get_species_knowledge.",
            )

        canon = canonical_class.strip().lower()
        if not canon:
            raise KnowledgeValidationError(
                message="canonical_class cannot be empty or whitespace.",
                detail="Received empty canonical_class in get_species_knowledge.",
            )

        # Validate against taxonomy before constructing search or calling vector DB
        tax_item = self.taxonomy.get_item(canon)
        if not tax_item:
            logger.warning(
                "get_species_knowledge requested for unknown canonical_class '%s'", canon
            )
            raise KnowledgeSpeciesNotFoundError(
                message=f"Species '{canon}' not found in taxonomy.",
                detail=f"canonical_class '{canon}' does not exist in taxonomy.yaml",
            )

        if limit > self.settings.knowledge_max_top_k:
            raise KnowledgeValidationError(
                message=f"limit {limit} exceeds maximum allowed {self.settings.knowledge_max_top_k}.",
                detail=f"Requested limit: {limit} > max: {self.settings.knowledge_max_top_k}",
            )

        display_en = tax_item.name_en
        display_vi = tax_item.name_vi
        category = tax_item.category or "other"

        # Construct a representative query from species names for semantic retrieval
        query_text = (
            f"{display_en} {display_vi or ''} nutrition botanical facts characteristics".strip()
        )
        search_req = KnowledgeSearchRequest(
            query=query_text,
            canonical_class=canon,
            limit=limit,
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
