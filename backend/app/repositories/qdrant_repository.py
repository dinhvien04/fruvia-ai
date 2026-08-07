"""
Qdrant Cloud repository for vector similarity search.
"""

from __future__ import annotations

import math
import time
from typing import Any

from qdrant_client import QdrantClient

from app.core.config import Settings, get_settings
from app.core.exceptions import QdrantCollectionNotFoundError, QdrantConnectionError
from app.core.logging import get_logger
from app.schemas.retrieval import RetrievalResult
from app.utils.taxonomy import get_taxonomy_manager

logger = get_logger(__name__)

MIN_TOP_K = 1
MAX_TOP_K = 20
MAX_RETRIES = 2
RETRY_DELAY_SEC = 1.0
EXPECTED_VECTOR_SIZE = 768


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
                raise QdrantConnectionError(
                    message="The image search service is temporarily unavailable.",
                    detail="QDRANT_URL or QDRANT_API_KEY is missing in environment settings.",
                )
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

    def get_health_status(self) -> tuple[bool, bool]:
        """
        Check Qdrant connectivity and collection availability in a single API call.

        Returns
        -------
        tuple[bool, bool]
            (qdrant_connected, collection_available)
        """
        try:
            collections_res = self.client.get_collections()
            existing_names = [col.name for col in collections_res.collections]
            collection_available = self.collection_name in existing_names
            return True, collection_available
        except Exception as e:
            logger.warning("Single Qdrant health check failed: %s", e)
            return False, False

    def query_similar(
        self,
        vector: list[float],
        top_k: int = 5,
        mode: str = "image",
        category: str = "all",
    ) -> list[RetrievalResult]:
        """
        Execute vector similarity search in Qdrant Cloud.

        Parameters
        ----------
        vector : list[float]
            768-dimensional L2-normalized query vector.
        top_k : int
            Number of similar items to retrieve (must be between 1 and 20).
        mode : str
            "image" for individual top images, or "class" for deduplicated top classes.
        category : str
            Category filter ("all", "fruit", "vegetable", "nut", "seed", "other").

        Returns
        -------
        list[RetrievalResult]
            List of mapped retrieval results.
        """
        if not (MIN_TOP_K <= top_k <= MAX_TOP_K):
            raise ValueError(f"top_k must be between {MIN_TOP_K} and {MAX_TOP_K}, got {top_k}")

        if len(vector) != EXPECTED_VECTOR_SIZE or not all(math.isfinite(x) for x in vector):
            raise ValueError(
                f"Query vector must be finite and exactly {EXPECTED_VECTOR_SIZE} dimensions."
            )

        # Calculate candidate limit based on mode and category filter
        if mode == "class" or category != "all":
            candidate_limit = max(
                top_k * self.settings.class_search_candidate_multiplier,
                self.settings.class_search_min_candidates,
            )
        else:
            candidate_limit = top_k

        logger.info(
            "Querying Qdrant collection '%s' (top_k=%d, limit=%d, mode=%s, category=%s)...",
            self.collection_name,
            top_k,
            candidate_limit,
            mode,
            category,
        )

        tax_mgr = get_taxonomy_manager()
        last_exception: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # Request payload only, skip vector retrieval for efficiency
                if hasattr(self.client, "query_points"):
                    query_response = self.client.query_points(
                        collection_name=self.collection_name,
                        query=vector,
                        limit=candidate_limit,
                        with_payload=True,
                        with_vectors=False,
                    )
                    hits = query_response.points
                else:
                    hits = self.client.search(
                        collection_name=self.collection_name,
                        query_vector=vector,
                        limit=candidate_limit,
                        with_payload=True,
                        with_vectors=False,
                    )

                raw_results: list[tuple[RetrievalResult, str]] = []
                for hit in hits:
                    payload = getattr(hit, "payload", {}) or {}
                    similarity_score = float(getattr(hit, "score", 0.0))

                    original_cls = str(
                        payload.get("original_class") or payload.get("class") or "unknown"
                    )
                    payload_canonical = payload.get("canonical_class")
                    payload_display = payload.get("display_name")

                    canonical_cls, display_en, display_vi, cat_cls = tax_mgr.resolve(
                        original_class=original_cls,
                        payload_canonical=payload_canonical,
                        payload_display=payload_display,
                    )

                    # Backward-compatible dataset resolution
                    ds_name = payload.get("dataset_name")
                    if not ds_name:
                        img_url = str(payload.get("image_url", ""))
                        if "fruits262" in img_url or "fruits-262" in img_url:
                            ds_name = "fruits262_full_original_v7"
                        else:
                            ds_name = "fruits360_original"

                    ds_version = payload.get("dataset_version") or (
                        "7" if "262" in ds_name else "1"
                    )

                    res = RetrievalResult(
                        original_class=original_cls,
                        canonical_class=canonical_cls,
                        display_name=display_en,
                        display_name_vi=display_vi,
                        category=cat_cls,
                        dataset_name=str(ds_name),
                        dataset_version=str(ds_version),
                        filename=str(payload.get("filename", "unknown")),
                        relative_path=str(payload.get("relative_path", "")),
                        original_split=str(
                            payload.get("original_split") or payload.get("source") or "unknown"
                        ),
                        similarity=similarity_score,
                        image_url=payload.get("image_url"),
                    )
                    raw_results.append((res, cat_cls))

                # Apply Category Filtering
                category_filtered: list[RetrievalResult] = []
                target_cat = category.lower().strip()
                for res, item_cat in raw_results:
                    if target_cat == "all" or item_cat == target_cat:
                        category_filtered.append(res)

                # Process results based on mode
                if mode == "class":
                    # Deduplicate by canonical_class
                    grouped: dict[str, list[RetrievalResult]] = {}
                    for item in category_filtered:
                        grouped.setdefault(item.canonical_class, []).append(item)

                    final_results: list[RetrievalResult] = []
                    for items in grouped.values():
                        rep_item = items[0]  # highest similarity match
                        rep_item.hit_count = len(items)
                        final_results.append(rep_item)
                        if len(final_results) >= top_k:
                            break
                    return final_results
                else:
                    # mode == "image"
                    return category_filtered[:top_k]

            except Exception as e:
                err_msg = str(e).lower()
                if "not found" in err_msg or "404" in err_msg:
                    logger.warning("Collection '%s' not found on Qdrant.", self.collection_name)
                    raise QdrantCollectionNotFoundError(
                        message=f"Collection '{self.collection_name}' is not available.",
                        detail=str(e),
                    ) from e

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
