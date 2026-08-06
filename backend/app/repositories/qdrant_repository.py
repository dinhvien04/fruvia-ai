"""
Qdrant Cloud repository for vector similarity search.
"""

from __future__ import annotations

import time
from typing import Any

from qdrant_client import QdrantClient

from app.core.config import Settings, get_settings
from app.core.exceptions import QdrantCollectionNotFoundError, QdrantConnectionError
from app.core.logging import get_logger
from app.schemas.retrieval import RetrievalResult

logger = get_logger(__name__)

MIN_TOP_K = 1
MAX_TOP_K = 20
MAX_RETRIES = 2
RETRY_DELAY_SEC = 1.0


class QdrantRepository:
    """
    Data repository for Qdrant Cloud vector search.

    Manages Qdrant client connection, health verification, collection validation,
    and cosine similarity vector search with automatic payload mapping to RetrievalResult.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        client: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client: Any = client
        self.collection_name = self.settings.qdrant_collection

    @property
    def client(self) -> QdrantClient:
        """Lazily initialize or return existing QdrantClient instance."""
        if self._client is None:
            if not self.settings.qdrant_url or not self.settings.qdrant_api_key:
                logger.warning("Qdrant URL or API Key is missing in configuration.")
            logger.info(
                "Initializing QdrantClient for endpoint '%s', collection '%s' (timeout=%ds)...",
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

    def is_connected(self) -> bool:
        """Check if Qdrant Cloud service is reachable."""
        try:
            self.client.get_collections()
            return True
        except Exception as e:
            logger.warning("Qdrant connection check failed: %s", e)
            return False

    def is_collection_available(self, collection_name: str | None = None) -> bool:
        """Check if specified collection exists on Qdrant Cloud."""
        target_collection = collection_name or self.collection_name
        try:
            collections_res = self.client.get_collections()
            existing_names = [col.name for col in collections_res.collections]
            is_present = target_collection in existing_names
            if not is_present:
                logger.warning(
                    "Target Qdrant collection '%s' not found. Available collections: %s",
                    target_collection,
                    existing_names,
                )
            return is_present
        except Exception as e:
            logger.warning(
                "Failed to check Qdrant collection '%s' availability: %s",
                target_collection,
                e,
            )
            return False

    def query_similar(self, vector: list[float], top_k: int = 5) -> list[RetrievalResult]:
        """
        Execute vector similarity search in Qdrant Cloud.

        Parameters
        ----------
        vector : list[float]
            768-dimensional L2-normalized query vector.
        top_k : int
            Number of similar items to retrieve (must be between 1 and 20).

        Returns
        -------
        list[RetrievalResult]
            List of mapped retrieval results.
        """
        if not (MIN_TOP_K <= top_k <= MAX_TOP_K):
            raise ValueError(f"top_k must be between {MIN_TOP_K} and {MAX_TOP_K}, got {top_k}")

        if not self.is_collection_available():
            raise QdrantCollectionNotFoundError(
                message=f"Collection '{self.collection_name}' is not available.",
                detail=f"Target collection '{self.collection_name}' does not exist on Qdrant server.",
            )

        logger.info(
            "Querying Qdrant collection '%s' (top_k=%d, vector_dim=%d)...",
            self.collection_name,
            top_k,
            len(vector),
        )

        last_exception: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # Use query_points or search depending on qdrant-client version
                if hasattr(self.client, "query_points"):
                    query_response = self.client.query_points(
                        collection_name=self.collection_name,
                        query=vector,
                        limit=top_k,
                        with_payload=True,
                    )
                    hits = query_response.points
                else:
                    hits = self.client.search(
                        collection_name=self.collection_name,
                        query_vector=vector,
                        limit=top_k,
                        with_payload=True,
                    )

                results: list[RetrievalResult] = []
                for hit in hits:
                    payload = getattr(hit, "payload", {}) or {}
                    similarity_score = float(getattr(hit, "score", 0.0))

                    # Ensure score is within [0.0, 1.0] bounds for cosine similarity
                    clamped_similarity = max(0.0, min(1.0, similarity_score))

                    res = RetrievalResult(
                        original_class=str(payload.get("original_class", "unknown")),
                        filename=str(payload.get("filename", "unknown")),
                        relative_path=str(payload.get("relative_path", "")),
                        original_split=str(
                            payload.get("original_split") or payload.get("source") or "unknown"
                        ),
                        similarity=clamped_similarity,
                    )
                    results.append(res)

                logger.info(
                    "Successfully retrieved %d results from Qdrant collection '%s'.",
                    len(results),
                    self.collection_name,
                )
                return results

            except Exception as e:
                last_exception = e
                logger.warning(
                    "Qdrant query attempt %d/%d failed: %s",
                    attempt,
                    MAX_RETRIES,
                    e,
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_SEC)

        logger.error(
            "All Qdrant query attempts failed for collection '%s': %s",
            self.collection_name,
            last_exception,
            exc_info=True,
        )
        raise QdrantConnectionError(
            message="Failed to query vector database.",
            detail=str(last_exception),
        ) from last_exception


_repo_instance: QdrantRepository | None = None


def get_qdrant_repository() -> QdrantRepository:
    """Return singleton QdrantRepository instance."""
    global _repo_instance
    if _repo_instance is None:
        _repo_instance = QdrantRepository()
    return _repo_instance
