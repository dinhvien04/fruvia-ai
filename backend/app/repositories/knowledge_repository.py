"""
Qdrant Cloud repository for semantic knowledge document retrieval.

Provides read-only access to BGE-M3 (1024D, Cosine) knowledge collections
with strict schema validation, capability checks, and exact payload filtering.
"""

from __future__ import annotations

import math
import time
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    QdrantCollectionNotFoundError,
    QdrantConnectionError,
    QdrantSchemaIncompatibleError,
)
from app.core.logging import get_logger
from app.repositories.qdrant_repository import is_keyword_index_type

logger = get_logger(__name__)

EXPECTED_KNOWLEDGE_VECTOR_SIZE = 1024
EXPECTED_KNOWLEDGE_DISTANCE = "Cosine"
MAX_RETRIES = 2
RETRY_DELAY_SEC = 1.0


class KnowledgeRepository:
    """
    Data repository for Qdrant Cloud knowledge vector search.

    Manages connection, health verification, 1024D Cosine collection schema validation,
    and capability-aware native keyword payload filtering (canonical_class, document_type).
    """

    def __init__(
        self,
        settings: Settings | None = None,
        client: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client: Any = client
        self.collection_name = self.settings.knowledge_qdrant_collection
        self._capabilities_cache: dict[str, tuple[float, set[str]]] = {}
        self._capabilities_ttl_sec: float = 60.0

    @property
    def client(self) -> QdrantClient:
        """Lazily initialize or return existing QdrantClient instance."""
        if self._client is None:
            if not self.settings.qdrant_url or not self.settings.qdrant_api_key:
                raise QdrantConnectionError(
                    message="The knowledge retrieval service is temporarily unavailable.",
                    detail="QDRANT_URL or QDRANT_API_KEY is missing in environment settings.",
                )
            logger.info(
                "Initializing Knowledge QdrantClient for endpoint '%s', collection '%s' (timeout=%ds)...",
                self.settings.qdrant_url,
                self.collection_name,
                self.settings.qdrant_timeout,
            )
            self._client = QdrantClient(
                url=self.settings.qdrant_url,
                api_key=self.settings.qdrant_api_key,
                timeout=self.settings.qdrant_timeout,
            )
        return self._client

    def get_filter_capabilities(self, collection_name: str | None = None) -> set[str]:
        """
        Inspect collection payload indexes and determine which fields can safely
        be used in native Qdrant query filters (e.g. 'canonical_class', 'document_type').

        Cached for 60 seconds per collection.
        Policy: Accepts ONLY exact 'keyword' index type.
        """
        target = collection_name or self.collection_name
        now = time.monotonic()

        cached = self._capabilities_cache.get(target)
        if cached is not None and (now - cached[0]) < self._capabilities_ttl_sec:
            return cached[1]

        supported_fields: set[str] = set()
        try:
            info = self.client.get_collection(collection_name=target)
            payload_schema = getattr(info, "payload_schema", None)
            if isinstance(payload_schema, dict):
                for field_name, schema_info in payload_schema.items():
                    if is_keyword_index_type(schema_info):
                        supported_fields.add(field_name.lower().strip())
        except Exception as e:
            logger.debug(
                "Failed to inspect payload schema for knowledge collection '%s': %s", target, e
            )
            supported_fields = set()

        self._capabilities_cache[target] = (now, supported_fields)
        return supported_fields

    def is_connected(self) -> bool:
        """Check if Qdrant Cloud service is reachable."""
        try:
            self.client.get_collections()
            return True
        except Exception as e:
            logger.warning("Knowledge Qdrant connection check failed: %s", e)
            return False

    def is_collection_available(self, collection_name: str | None = None) -> bool:
        """Check if specified knowledge collection exists on Qdrant Cloud."""
        target_collection = collection_name or self.collection_name
        try:
            collections_res = self.client.get_collections()
            existing_names = [col.name for col in collections_res.collections]
            return target_collection in existing_names
        except Exception as e:
            logger.warning(
                "Failed to check Qdrant knowledge collection '%s' availability: %s",
                target_collection,
                e,
            )
            return False

    def validate_collection_schema(self, collection_name: str | None = None) -> dict[str, Any]:
        """
        Validate target Qdrant knowledge collection schema for vector size (1024D),
        distance metric (Cosine), status (GREEN or YELLOW), and point counts.

        Returns
        -------
        dict[str, Any]
            Collection metadata summary.

        Raises
        ------
        QdrantCollectionNotFoundError
            If collection does not exist.
        QdrantSchemaIncompatibleError
            If vector size or distance metric does not match expected BGE-M3 configuration.
        """
        target = collection_name or self.collection_name
        try:
            info = self.client.get_collection(collection_name=target)
        except Exception as e:
            err_str = str(e).lower()
            if "not found" in err_str or "404" in err_str:
                raise QdrantCollectionNotFoundError(
                    message=f"Knowledge collection '{target}' is not available.",
                    detail=str(e),
                ) from e
            raise QdrantConnectionError(
                message="Failed to connect to vector database for knowledge retrieval.",
                detail=str(e),
            ) from e

        config = getattr(info, "config", None)
        params = getattr(config, "params", None)
        vectors_config = getattr(params, "vectors", None)

        vector_size: int | None = None
        distance_metric: str | None = None

        if vectors_config is not None:
            if hasattr(vectors_config, "size"):
                vector_size = getattr(vectors_config, "size", None)
                distance_metric = str(getattr(vectors_config, "distance", ""))
            elif isinstance(vectors_config, dict):
                first_vec = next(iter(vectors_config.values()), None)
                if first_vec:
                    vector_size = getattr(first_vec, "size", None)
                    distance_metric = str(getattr(first_vec, "distance", ""))

        if vector_size is not None and vector_size != EXPECTED_KNOWLEDGE_VECTOR_SIZE:
            raise QdrantSchemaIncompatibleError(
                message=f"Knowledge collection '{target}' vector size {vector_size} is incompatible with expected {EXPECTED_KNOWLEDGE_VECTOR_SIZE}D.",
                detail=f"Expected {EXPECTED_KNOWLEDGE_VECTOR_SIZE}, found {vector_size}.",
            )

        if distance_metric and EXPECTED_KNOWLEDGE_DISTANCE.lower() not in distance_metric.lower():
            raise QdrantSchemaIncompatibleError(
                message=f"Knowledge collection '{target}' distance '{distance_metric}' is incompatible with expected '{EXPECTED_KNOWLEDGE_DISTANCE}'.",
                detail=f"Expected {EXPECTED_KNOWLEDGE_DISTANCE}, found {distance_metric}.",
            )

        points_count = (
            getattr(info, "points_count", None) or getattr(info, "vectors_count", None) or 0
        )
        raw_status = getattr(info, "status", "unknown")
        status_name = getattr(raw_status, "name", str(raw_status)).upper()

        if status_name not in {"GREEN", "YELLOW"}:
            raise QdrantSchemaIncompatibleError(
                message=f"Knowledge collection '{target}' status is {status_name} (unhealthy/not ready).",
                detail=f"Expected collection status GREEN or YELLOW, found {status_name}.",
            )

        if vector_size is None or distance_metric is None:
            raise QdrantSchemaIncompatibleError(
                message=f"Could not verify vector schema for knowledge collection '{target}'.",
                detail="Collection vector size or distance metric could not be determined.",
            )

        logger.info(
            "Validated Knowledge Qdrant collection '%s': status=%s, points=%s, vector_size=%s, distance=%s",
            target,
            status_name,
            points_count,
            vector_size,
            distance_metric,
        )

        return {
            "collection_name": target,
            "status": status_name,
            "points_count": points_count,
            "vector_size": vector_size,
            "distance": distance_metric,
        }

    def get_health_status(self) -> tuple[bool, bool, bool, dict[str, Any] | None]:
        """
        Check Qdrant connectivity, knowledge collection availability, and schema validity.

        Returns
        -------
        tuple[bool, bool, bool, dict[str, Any] | None]
            (qdrant_connected, collection_available, schema_valid, schema_info)
        """
        try:
            collections_res = self.client.get_collections()
            existing_names = [col.name for col in collections_res.collections]
            collection_available = self.collection_name in existing_names
            if not collection_available:
                return True, False, False, None

            try:
                schema_info = self.validate_collection_schema(self.collection_name)
                return True, True, True, schema_info
            except QdrantSchemaIncompatibleError as schema_err:
                logger.warning("Knowledge collection schema is incompatible: %s", schema_err)
                return True, True, False, None
        except Exception as e:
            logger.warning("Knowledge health check failed: %s", e)
            return False, False, False, None

    def build_qdrant_filter(
        self,
        canonical_class: str | None = None,
        document_type: str | None = None,
        supported_fields: set[str] | None = None,
    ) -> Filter | None:
        """
        Build a native Qdrant Filter object for keyword-indexed fields.
        """
        conditions: list[FieldCondition] = []
        caps = (
            supported_fields
            if supported_fields is not None
            else self.get_filter_capabilities(self.collection_name)
        )

        if canonical_class and canonical_class.strip():
            canon_val = canonical_class.strip().lower()
            if "canonical_class" in caps:
                conditions.append(
                    FieldCondition(key="canonical_class", match=MatchValue(value=canon_val))
                )

        if document_type and document_type.strip():
            doc_type_val = document_type.strip().lower()
            if "document_type" in caps:
                conditions.append(
                    FieldCondition(key="document_type", match=MatchValue(value=doc_type_val))
                )

        if not conditions:
            return None

        return Filter(must=conditions)  # type: ignore[arg-type]

    def query_knowledge(
        self,
        vector: list[float],
        top_k: int = 5,
        canonical_class: str | None = None,
        document_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Execute vector similarity search in Qdrant Cloud for knowledge documents.

        Parameters
        ----------
        vector : list[float]
            1024-dimensional L2-normalized query vector.
        top_k : int
            Number of documents to retrieve.
        canonical_class : str | None
            Optional canonical class filter.
        document_type : str | None
            Optional document type filter (e.g., 'nutrition', 'botanical', 'general').

        Returns
        -------
        list[dict[str, Any]]
            Raw retrieved hit dictionaries with score and payload.
        """
        if not (1 <= top_k <= self.settings.knowledge_max_top_k):
            raise ValueError(
                f"top_k must be between 1 and {self.settings.knowledge_max_top_k}, got {top_k}"
            )

        if len(vector) != EXPECTED_KNOWLEDGE_VECTOR_SIZE or not all(
            math.isfinite(x) for x in vector
        ):
            raise ValueError(
                f"Query vector must be finite and exactly {EXPECTED_KNOWLEDGE_VECTOR_SIZE} dimensions."
            )

        filter_caps = self.get_filter_capabilities(self.collection_name)
        qdrant_filter = self.build_qdrant_filter(
            canonical_class=canonical_class,
            document_type=document_type,
            supported_fields=filter_caps,
        )

        logger.info(
            "Querying Knowledge collection '%s' (top_k=%d, canonical_class=%s, document_type=%s, native_filter=%s)...",
            self.collection_name,
            top_k,
            canonical_class,
            document_type,
            bool(qdrant_filter),
        )

        last_exception: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                hits: list[Any] = []
                try:
                    if hasattr(self.client, "query_points"):
                        query_response = self.client.query_points(
                            collection_name=self.collection_name,
                            query=vector,
                            query_filter=qdrant_filter,
                            limit=top_k,
                            with_payload=True,
                            with_vectors=False,
                        )
                        hits = query_response.points
                    else:
                        hits = self.client.search(
                            collection_name=self.collection_name,
                            query_vector=vector,
                            query_filter=qdrant_filter,
                            limit=top_k,
                            with_payload=True,
                            with_vectors=False,
                        )
                except Exception as query_err:
                    if qdrant_filter is not None:
                        logger.warning(
                            "Native Qdrant knowledge filter query failed (%s). Falling back to client-side filtering.",
                            query_err,
                        )
                        qdrant_filter = None
                        continue
                    raise query_err

                raw_hits: list[dict[str, Any]] = []
                target_canon = canonical_class.lower().strip() if canonical_class else None
                target_dtype = document_type.lower().strip() if document_type else None

                for hit in hits:
                    payload = getattr(hit, "payload", {}) or {}
                    score = float(getattr(hit, "score", 0.0))

                    # Client-side fallback filter check if native filter was omitted or partial
                    hit_canon = str(payload.get("canonical_class", "")).lower().strip()
                    hit_dtype = str(payload.get("document_type", "")).lower().strip()

                    if target_canon and hit_canon != target_canon:
                        continue
                    if target_dtype and hit_dtype != target_dtype:
                        continue

                    raw_hits.append(
                        {
                            "id": getattr(hit, "id", None),
                            "score": score,
                            "payload": payload,
                        }
                    )

                return raw_hits[:top_k]

            except Exception as e:
                err_msg = str(e).lower()
                if "not found" in err_msg or "404" in err_msg:
                    raise QdrantCollectionNotFoundError(
                        message=f"Knowledge collection '{self.collection_name}' is not available.",
                        detail=str(e),
                    ) from e
                last_exception = e
                logger.warning(
                    "Knowledge Qdrant query attempt %d/%d failed: %s",
                    attempt,
                    MAX_RETRIES,
                    e,
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_SEC)

        logger.error(
            "All Knowledge Qdrant query attempts failed for collection '%s': %s",
            self.collection_name,
            last_exception,
            exc_info=True,
        )
        raise QdrantConnectionError(
            message="Failed to query knowledge vector database after multiple attempts.",
            detail=str(last_exception) if last_exception else "Unknown error",
        ) from last_exception


_knowledge_repo_instance: KnowledgeRepository | None = None


def get_knowledge_repository() -> KnowledgeRepository:
    """Return singleton KnowledgeRepository instance."""
    global _knowledge_repo_instance
    if _knowledge_repo_instance is None:
        _knowledge_repo_instance = KnowledgeRepository()
    return _knowledge_repo_instance
