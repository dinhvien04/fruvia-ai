"""
Qdrant Cloud repository for vector similarity search.
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
from app.schemas.retrieval import RetrievalResult
from app.utils.taxonomy import get_taxonomy_manager

logger = get_logger(__name__)

MIN_TOP_K = 1
MAX_TOP_K = 20
MAX_RETRIES = 2
RETRY_DELAY_SEC = 1.0
EXPECTED_VECTOR_SIZE = 768
EXPECTED_DISTANCE_METRIC = "Cosine"


def is_keyword_index_type(schema_info: Any) -> bool:
    """
    Check if schema_info represents an exact keyword payload index in Qdrant.
    Rejects text, integer, float, geo, bool, or None schemas.
    """
    if schema_info is None:
        return False
    data_type = (
        getattr(schema_info, "data_type", None) or getattr(schema_info, "type", None) or schema_info
    )
    if hasattr(data_type, "value"):
        data_type = data_type.value
    dt_str = str(data_type).lower().strip()
    return dt_str in {"keyword", "payloadschematype.keyword"}


class QdrantRepository:
    """
    Data repository for Qdrant Cloud vector search.

    Manages Qdrant client connection, health verification, collection validation,
    native payload filtering, and cosine similarity vector search with automatic
    payload mapping to RetrievalResult.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        client: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client: Any = client
        self.collection_name = self.settings.active_gallery_collection
        self._capabilities_cache: dict[str, tuple[float, set[str]]] = {}
        self._capabilities_ttl_sec: float = 60.0

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

    def get_filter_capabilities(self, collection_name: str | None = None) -> set[str]:
        """
        Inspect collection payload indexes and determine which fields can safely
        be used in native Qdrant query filters without falling back or failing.

        Cached for 60 seconds per collection.
        Policy:
        - Accepts ONLY exact 'keyword' index type (never 'text').
        - Enforces collection safety policy: only collections listed in
          `native_filter_safe_collections` (or verified safe) are permitted to use
          native filtering, ensuring legacy collections with partial payload coverage
          safely default to robust Python-level filtering.
        """
        target = collection_name or self.collection_name
        now = time.monotonic()

        cached = self._capabilities_cache.get(target)
        if cached is not None and (now - cached[0]) < self._capabilities_ttl_sec:
            return cached[1]

        supported_fields: set[str] = set()

        # Enforce safety check against native_filter_safe_collections (fails closed if empty or target not listed)
        safe_collections = self.settings.native_filter_safe_collection_list
        if target not in safe_collections:
            logger.debug(
                "Collection '%s' is not in native_filter_safe_collections; returning empty filter capabilities for safe client filtering.",
                target,
            )
            self._capabilities_cache[target] = (now, supported_fields)
            return supported_fields

        try:
            info = self.client.get_collection(collection_name=target)
            payload_schema = getattr(info, "payload_schema", None)
            if isinstance(payload_schema, dict):
                for field_name, schema_info in payload_schema.items():
                    if is_keyword_index_type(schema_info):
                        supported_fields.add(field_name.lower().strip())
        except Exception as e:
            logger.debug("Failed to inspect payload schema for '%s': %s", target, e)
            supported_fields = set()

        self._capabilities_cache[target] = (now, supported_fields)
        return supported_fields

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

    def validate_collection_schema(self, collection_name: str | None = None) -> dict[str, Any]:
        """
        Validate target Qdrant collection schema for vector size (768),
        distance metric (Cosine), status, and point counts.

        Returns
        -------
        dict[str, Any]
            Collection metadata summary including points_count and vector_size.

        Raises
        ------
        QdrantCollectionNotFoundError
            If collection does not exist.
        QdrantSchemaIncompatibleError
            If vector size or distance metric does not match expected DINOv2 configuration.
        """
        target = collection_name or self.collection_name
        try:
            info = self.client.get_collection(collection_name=target)
        except Exception as e:
            err_str = str(e).lower()
            if "not found" in err_str or "404" in err_str:
                raise QdrantCollectionNotFoundError(
                    message=f"Collection '{target}' is not available.",
                    detail=str(e),
                ) from e
            raise QdrantConnectionError(
                message="Failed to connect to vector database.",
                detail=str(e),
            ) from e

        config = getattr(info, "config", None)
        params = getattr(config, "params", None)
        vectors_config = getattr(params, "vectors", None)

        vector_size: int | None = None
        distance_metric: str | None = None

        if vectors_config is not None:
            # Single vector configuration
            if hasattr(vectors_config, "size"):
                vector_size = getattr(vectors_config, "size", None)
                distance_metric = str(getattr(vectors_config, "distance", ""))
            # Named vectors dictionary configuration
            elif isinstance(vectors_config, dict):
                first_vec = next(iter(vectors_config.values()), None)
                if first_vec:
                    vector_size = getattr(first_vec, "size", None)
                    distance_metric = str(getattr(first_vec, "distance", ""))

        if vector_size is not None and vector_size != EXPECTED_VECTOR_SIZE:
            raise QdrantSchemaIncompatibleError(
                message=f"Collection '{target}' vector size {vector_size} is incompatible with expected {EXPECTED_VECTOR_SIZE}D.",
                detail=f"Expected {EXPECTED_VECTOR_SIZE}, found {vector_size}.",
            )

        if distance_metric and EXPECTED_DISTANCE_METRIC.lower() not in distance_metric.lower():
            raise QdrantSchemaIncompatibleError(
                message=f"Collection '{target}' distance '{distance_metric}' is incompatible with expected '{EXPECTED_DISTANCE_METRIC}'.",
                detail=f"Expected {EXPECTED_DISTANCE_METRIC}, found {distance_metric}.",
            )

        points_count = (
            getattr(info, "points_count", None) or getattr(info, "vectors_count", None) or 0
        )
        raw_status = getattr(info, "status", "unknown")
        status_name = getattr(raw_status, "name", str(raw_status)).upper()

        # Explicit status policy: GREEN and YELLOW are ready; RED, GREY, ERROR, and unknown/other fail closed
        if status_name not in {"GREEN", "YELLOW"}:
            raise QdrantSchemaIncompatibleError(
                message=f"Collection '{target}' status is {status_name} (unhealthy/not ready).",
                detail=f"Expected collection status GREEN or YELLOW, found {status_name}.",
            )

        if vector_size is None or distance_metric is None:
            raise QdrantSchemaIncompatibleError(
                message=f"Could not verify vector schema for collection '{target}'.",
                detail="Collection vector size or distance metric could not be determined.",
            )

        logger.info(
            "Validated Qdrant collection '%s': status=%s, points=%s, vector_size=%s, distance=%s",
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
        Check Qdrant connectivity, collection availability, and schema validity in a single API inspection.

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
                logger.warning("Qdrant collection schema is incompatible: %s", schema_err)
                return True, True, False, None
        except Exception as e:
            logger.warning("Qdrant health check failed: %s", e)
            return False, False, False, None

    def build_qdrant_filter(
        self,
        category: str | None = None,
        canonical_class: str | None = None,
        source_dataset: str | None = None,
        dataset_name: str | None = None,
        supported_fields: set[str] | None = None,
    ) -> Filter | None:
        """
        Build a native Qdrant Filter object ONLY for fields verified to have
        payload keyword index capabilities on the target collection.
        """
        conditions: list[FieldCondition] = []
        caps = (
            supported_fields
            if supported_fields is not None
            else self.get_filter_capabilities(self.collection_name)
        )

        if category and category.lower().strip() not in {"all", ""}:
            cat_val = category.lower().strip()
            if "category" in caps:
                conditions.append(FieldCondition(key="category", match=MatchValue(value=cat_val)))

        if canonical_class and canonical_class.strip():
            canon_val = canonical_class.strip().lower()
            if "canonical_class" in caps:
                conditions.append(
                    FieldCondition(key="canonical_class", match=MatchValue(value=canon_val))
                )

        if source_dataset and source_dataset.strip():
            source_val = source_dataset.strip().lower()
            if "source_dataset" in caps:
                conditions.append(
                    FieldCondition(key="source_dataset", match=MatchValue(value=source_val))
                )

        if dataset_name and dataset_name.strip():
            ds_val = dataset_name.strip()
            if "dataset_name" in caps:
                conditions.append(
                    FieldCondition(key="dataset_name", match=MatchValue(value=ds_val))
                )

        if not conditions:
            return None

        return Filter(must=conditions)  # type: ignore[arg-type]

    def query_similar(
        self,
        vector: list[float],
        top_k: int = 5,
        mode: str = "image",
        category: str = "all",
        canonical_class: str | None = None,
        source_dataset: str | None = None,
        dataset_name: str | None = None,
        use_native_filter: bool = True,
    ) -> list[RetrievalResult]:
        """
        Execute vector similarity search in Qdrant Cloud with capability-aware native filtering
        and graceful Python-level fallback for unindexed/legacy payloads.

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
        canonical_class : str | None
            Optional canonical class filter.
        source_dataset : str | None
            Optional source dataset filter.
        dataset_name : str | None
            Optional dataset name filter.
        use_native_filter : bool
            Whether to attempt native Qdrant filtering for supported fields.

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

        # Inspect supported payload filter capabilities
        filter_caps = (
            self.get_filter_capabilities(self.collection_name) if use_native_filter else set()
        )

        # Calculate initial candidate limit and maximum candidate cap
        max_cap = self.settings.class_search_max_candidates
        has_client_filtering_needed = (
            (category != "all" and "category" not in filter_caps)
            or (canonical_class and "canonical_class" not in filter_caps)
            or (source_dataset and "source_dataset" not in filter_caps)
            or (dataset_name and "dataset_name" not in filter_caps)
        )

        if mode == "class" or category != "all" or has_client_filtering_needed:
            initial_limit = max(
                top_k * self.settings.class_search_candidate_multiplier,
                self.settings.class_search_min_candidates,
            )
        else:
            initial_limit = top_k

        initial_limit = min(initial_limit, max_cap)

        qdrant_filter = (
            self.build_qdrant_filter(
                category=category,
                canonical_class=canonical_class,
                source_dataset=source_dataset,
                dataset_name=dataset_name,
                supported_fields=filter_caps,
            )
            if use_native_filter
            else None
        )

        logger.info(
            "Querying Qdrant collection '%s' (top_k=%d, initial_limit=%d, max_cap=%d, mode=%s, category=%s, native_filter=%s)...",
            self.collection_name,
            top_k,
            initial_limit,
            max_cap,
            mode,
            category,
            bool(qdrant_filter),
        )

        tax_mgr = get_taxonomy_manager()
        last_exception: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                candidate_limit = initial_limit
                while True:
                    # Request payload only, skip vector retrieval for efficiency
                    hits: list[Any] = []
                    try:
                        if hasattr(self.client, "query_points"):
                            query_response = self.client.query_points(
                                collection_name=self.collection_name,
                                query=vector,
                                query_filter=qdrant_filter,
                                limit=candidate_limit,
                                with_payload=True,
                                with_vectors=False,
                            )
                            hits = query_response.points
                        else:
                            hits = self.client.search(
                                collection_name=self.collection_name,
                                query_vector=vector,
                                query_filter=qdrant_filter,
                                limit=candidate_limit,
                                with_payload=True,
                                with_vectors=False,
                            )
                    except Exception as query_err:
                        # If native filter failed (e.g. unindexed field in legacy collection), retry without filter
                        if qdrant_filter is not None:
                            logger.warning(
                                "Native Qdrant filter query failed (%s). Falling back to client-side filtering.",
                                query_err,
                            )
                            qdrant_filter = None
                            continue
                        raise query_err

                    raw_results: list[tuple[RetrievalResult, str, str, str]] = []
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

                        # Explicit source_dataset and dataset_name resolution
                        raw_source = payload.get("source_dataset")
                        raw_ds = payload.get("dataset_name")

                        img_url = str(payload.get("image_url", ""))
                        if not raw_source:
                            if (
                                "fruits262" in img_url
                                or "fruits-262" in img_url
                                or (raw_ds and "262" in str(raw_ds))
                            ):
                                raw_source = "fruits262"
                            elif "packeat" in img_url or (raw_ds and "packeat" in str(raw_ds)):
                                raw_source = "packeat"
                            else:
                                raw_source = "fruits360"

                        if not raw_ds:
                            if raw_source == "fruits262":
                                raw_ds = "fruits262_full_original_v7"
                            elif raw_source == "packeat":
                                raw_ds = "packeat_dinov2_base_v1"
                            else:
                                raw_ds = "fruits360_original"

                        ds_version = payload.get("dataset_version") or (
                            "7" if "262" in str(raw_ds) else "1"
                        )

                        res = RetrievalResult(
                            original_class=original_cls,
                            canonical_class=canonical_cls,
                            display_name=display_en,
                            display_name_vi=display_vi,
                            category=cat_cls,
                            dataset_name=str(raw_ds),
                            dataset_version=str(ds_version),
                            filename=str(payload.get("filename", "unknown")),
                            relative_path=str(payload.get("relative_path", "")),
                            original_split=str(
                                payload.get("original_split") or payload.get("source") or "unknown"
                            ),
                            similarity=similarity_score,
                            image_url=payload.get("image_url"),
                        )
                        raw_results.append((res, cat_cls, str(raw_source), str(raw_ds)))

                    # Apply exact Payload Filtering (client-side fallback where native filter wasn't applied or was partial)
                    filtered_results: list[RetrievalResult] = []
                    target_cat = category.lower().strip()
                    target_canon = canonical_class.lower().strip() if canonical_class else None
                    target_source = source_dataset.lower().strip() if source_dataset else None
                    target_ds = dataset_name.lower().strip() if dataset_name else None

                    for res, item_cat, item_source, item_ds in raw_results:
                        if target_cat not in {"all", ""} and item_cat != target_cat:
                            continue
                        if target_canon and res.canonical_class.lower() != target_canon:
                            continue
                        if target_source and item_source.lower() != target_source:
                            continue
                        if target_ds and item_ds.lower() != target_ds:
                            continue
                        filtered_results.append(res)

                    # Check exit criteria or need for candidate expansion
                    if mode == "class":
                        grouped: dict[str, list[RetrievalResult]] = {}
                        for item in filtered_results:
                            grouped.setdefault(item.canonical_class, []).append(item)

                        distinct_count = len(grouped)
                        if (
                            distinct_count >= top_k
                            or candidate_limit >= max_cap
                            or len(hits) < candidate_limit
                        ):
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
                        if (
                            len(filtered_results) >= top_k
                            or candidate_limit >= max_cap
                            or len(hits) < candidate_limit
                        ):
                            return filtered_results[:top_k]

                    # Expand candidate pool if top_k criteria not yet met
                    next_limit = min(candidate_limit * 2, max_cap)
                    if next_limit <= candidate_limit:
                        # Cannot expand further
                        if mode == "class":
                            grouped = {}
                            for item in filtered_results:
                                grouped.setdefault(item.canonical_class, []).append(item)
                            final_results = []
                            for items in grouped.values():
                                rep_item = items[0]
                                rep_item.hit_count = len(items)
                                final_results.append(rep_item)
                                if len(final_results) >= top_k:
                                    break
                            return final_results
                        return filtered_results[:top_k]

                    logger.debug(
                        "Expanding Qdrant candidate pool from %d to %d...",
                        candidate_limit,
                        next_limit,
                    )
                    candidate_limit = next_limit

            except Exception as e:
                err_msg = str(e).lower()
                if "not found" in err_msg or "404" in err_msg:
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
            message="Failed to query vector database after multiple attempts.",
            detail=str(last_exception) if last_exception else "Unknown error",
        ) from last_exception


_repo_instance: QdrantRepository | None = None


def get_qdrant_repository() -> QdrantRepository:
    """Return singleton QdrantRepository instance."""
    global _repo_instance
    if _repo_instance is None:
        _repo_instance = QdrantRepository()
    return _repo_instance
