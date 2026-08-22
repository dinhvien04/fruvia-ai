"""
Qdrant Cloud repository for semantic knowledge document retrieval.

Provides read-only access to BGE-M3 (1024D, Cosine) knowledge collections
with strict schema validation, keyword payload index validation, and native
grouped retrieval (group_by='document_id', group_size=1) to prevent duplicate
chunks from the same document dominating search results.
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
REQUIRED_KNOWLEDGE_KEYWORD_INDEXES = {"canonical_class", "document_type", "document_id"}
MAX_RETRIES = 2
RETRY_DELAY_SEC = 1.0


class KnowledgeRepository:
    """
    Data repository for Qdrant Cloud knowledge vector search.

    Manages connection, health verification, 1024D Cosine collection schema validation,
    strict keyword payload index verification (canonical_class, document_type, document_id),
    and native grouped semantic retrieval via query_points_groups().
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
        Inspect collection payload indexes and determine which fields have
        verified 'keyword' index type.

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
                "Failed to inspect payload schema for knowledge collection '%s': %s",
                target,
                e,
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
        Validate target Qdrant knowledge collection schema for:
        - Collection existence
        - 1024D vector size
        - Cosine distance metric
        - Healthy Qdrant status (GREEN or YELLOW)
        - Required keyword payload indexes: canonical_class, document_type, document_id

        Fails closed with zero runtime mutations.

        Returns
        -------
        dict[str, Any]
            Collection metadata summary.

        Raises
        ------
        QdrantCollectionNotFoundError
            If collection does not exist.
        QdrantSchemaIncompatibleError
            If vector size, distance metric, status, or required keyword indexes are missing/incompatible.
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

        # Validate required keyword payload indexes
        payload_schema = getattr(info, "payload_schema", {}) or {}
        indexed_keywords: set[str] = set()
        if isinstance(payload_schema, dict):
            for field_name, schema_info in payload_schema.items():
                if is_keyword_index_type(schema_info):
                    indexed_keywords.add(field_name.lower().strip())

        missing_indexes = REQUIRED_KNOWLEDGE_KEYWORD_INDEXES - indexed_keywords
        if missing_indexes:
            raise QdrantSchemaIncompatibleError(
                message=f"Knowledge collection '{target}' is missing required keyword payload indexes: {sorted(missing_indexes)}.",
                detail=f"Required keyword indexes: {sorted(REQUIRED_KNOWLEDGE_KEYWORD_INDEXES)}, found: {sorted(indexed_keywords)}.",
            )

        logger.info(
            "Validated Knowledge Qdrant collection '%s': status=%s, points=%s, vector_size=%s, distance=%s, keyword_indexes=%s",
            target,
            status_name,
            points_count,
            vector_size,
            distance_metric,
            sorted(indexed_keywords),
        )

        return {
            "collection_name": target,
            "status": status_name,
            "points_count": points_count,
            "vector_size": vector_size,
            "distance": distance_metric,
            "keyword_indexes": sorted(indexed_keywords),
        }

    def get_health_status(self) -> tuple[bool, bool, bool, dict[str, Any] | None]:
        """
        Check Qdrant connectivity, knowledge collection availability, and full schema validity.

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
        canonical_class: str,
        document_type: str | None = None,
    ) -> Filter:
        """
        Build exact native Qdrant Filter for canonical_class and optional document_type.
        """
        conditions: list[FieldCondition] = [
            FieldCondition(
                key="canonical_class",
                match=MatchValue(value=canonical_class.strip().lower()),
            )
        ]

        if document_type and document_type.strip():
            conditions.append(
                FieldCondition(
                    key="document_type",
                    match=MatchValue(value=document_type.strip().lower()),
                )
            )

        return Filter(must=conditions)  # type: ignore[arg-type]

    def query_knowledge_grouped(
        self,
        vector: list[float],
        canonical_class: str,
        document_type: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Execute grouped vector similarity search in Qdrant Cloud for knowledge documents.

        Groups multi-chunk passages by 'document_id' and returns the top chunk for each unique document.

        Parameters
        ----------
        vector : list[float]
            1024-dimensional L2-normalized query vector.
        canonical_class : str
            Required canonical species identifier.
        document_type : str | None
            Optional document type filter (e.g., 'nutrition', 'encyclopedia', 'taxonomy_scientific').
        limit : int
            Number of distinct knowledge documents to retrieve.

        Returns
        -------
        list[dict[str, Any]]
            Flattened list of top hit per document group, containing id, document_id, score, and payload.
        """
        if not (1 <= limit <= self.settings.knowledge_max_top_k):
            raise ValueError(
                f"limit must be between 1 and {self.settings.knowledge_max_top_k}, got {limit}"
            )

        if not canonical_class or not canonical_class.strip():
            raise ValueError("canonical_class is required for knowledge search.")

        if len(vector) != EXPECTED_KNOWLEDGE_VECTOR_SIZE or not all(
            math.isfinite(x) for x in vector
        ):
            raise ValueError(
                f"Query vector must be finite and exactly {EXPECTED_KNOWLEDGE_VECTOR_SIZE} dimensions."
            )

        qdrant_filter = self.build_qdrant_filter(
            canonical_class=canonical_class,
            document_type=document_type,
        )

        logger.info(
            "Querying Knowledge grouped collection '%s' (group_by=document_id, limit=%d, group_size=1, canonical_class=%s, document_type=%s)...",
            self.collection_name,
            limit,
            canonical_class,
            document_type,
        )

        last_exception: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # Native Qdrant grouped query points execution
                groups_response = self.client.query_points_groups(
                    collection_name=self.collection_name,
                    query=vector,
                    query_filter=qdrant_filter,
                    group_by="document_id",
                    limit=limit,
                    group_size=1,
                    with_payload=True,
                    with_vectors=False,
                )

                raw_hits: list[dict[str, Any]] = []
                groups = getattr(groups_response, "groups", []) or []

                for group in groups:
                    hits = getattr(group, "hits", []) or []
                    if not hits:
                        continue
                    # Flatten to top hit per group
                    top_hit = hits[0]
                    payload = getattr(top_hit, "payload", {}) or {}
                    score = float(getattr(top_hit, "score", 0.0))
                    hit_id = getattr(top_hit, "id", None)
                    group_doc_id = str(getattr(group, "id", "") or payload.get("document_id", ""))

                    raw_hits.append(
                        {
                            "id": hit_id,
                            "document_id": group_doc_id,
                            "score": score,
                            "payload": payload,
                        }
                    )

                return raw_hits[:limit]

            except Exception as e:
                err_msg = str(e).lower()
                if "not found" in err_msg or "404" in err_msg:
                    raise QdrantCollectionNotFoundError(
                        message=f"Knowledge collection '{self.collection_name}' is not available.",
                        detail=str(e),
                    ) from e
                last_exception = e
                logger.warning(
                    "Knowledge Qdrant grouped query attempt %d/%d failed: %s",
                    attempt,
                    MAX_RETRIES,
                    e,
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_SEC)

        logger.error(
            "All Knowledge Qdrant grouped query attempts failed for collection '%s': %s",
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
