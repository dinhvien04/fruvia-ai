"""
Business logic service for fruit image retrieval via vector search.
"""

from __future__ import annotations

import time

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.ml.image_encoder import ImageEncoder, get_image_encoder
from app.repositories.qdrant_repository import QdrantRepository, get_qdrant_repository
from app.schemas.retrieval import (
    QueryInfo,
    RetrievalQuality,
    RetrievalResponse,
    RetrievalTiming,
)
from app.utils.image_validation import validate_upload

logger = get_logger(__name__)


class RetrievalService:
    """
    Service orchestrating image validation, DINOv2 feature extraction,
    and Qdrant Cloud vector search with performance timing and quality evaluation.
    """

    def __init__(
        self,
        image_encoder: ImageEncoder | None = None,
        qdrant_repository: QdrantRepository | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.encoder = image_encoder or get_image_encoder()
        self.qdrant_repo = qdrant_repository or get_qdrant_repository()
        self.settings = settings or get_settings()

    def retrieve_similar(
        self,
        file_bytes: bytes,
        filename: str,
        top_k: int = 5,
        mode: str = "image",
        category: str = "all",
        content_type: str | None = None,
    ) -> RetrievalResponse:
        """
        Process uploaded image bytes and retrieve visually similar fruit images.

        Parameters
        ----------
        file_bytes : bytes
            Raw image file payload.
        filename : str
            Original filename of the uploaded image.
        top_k : int
            Number of similar results to retrieve (1 to 20).
        mode : str
            Retrieval mode: "image" or "class".
        category : str
            Category filter: "all", "fruit", "vegetable", "nut", "seed", "other".

        Returns
        -------
        RetrievalResponse
            Retrieval query metadata, results with similarity scores, and execution timing.
        """
        t_start = time.perf_counter()

        logger.info(
            "Processing retrieval request for file '%s' (bytes=%d, top_k=%d, mode=%s, category=%s)...",
            filename,
            len(file_bytes),
            top_k,
            mode,
            category,
        )

        # 1. Validate image format, size, and integrity
        t_val_start = time.perf_counter()
        pil_image, _ = validate_upload(
            data=file_bytes,
            filename=filename,
            max_bytes=self.settings.max_upload_bytes,
            content_type=content_type,
        )
        validation_ms = round((time.perf_counter() - t_val_start) * 1000, 2)

        # 2. Extract 768-dim L2-normalized feature vector using DINOv2
        t_emb_start = time.perf_counter()
        query_vector = self.encoder.encode_image(pil_image)
        embedding_ms = round((time.perf_counter() - t_emb_start) * 1000, 2)

        # 3. Perform cosine similarity vector search in Qdrant Cloud
        t_search_start = time.perf_counter()
        results = self.qdrant_repo.query_similar(
            vector=query_vector, top_k=top_k, mode=mode, category=category
        )
        vector_search_ms = round((time.perf_counter() - t_search_start) * 1000, 2)

        # 4. Calculate total execution time in milliseconds
        total_ms = round((time.perf_counter() - t_start) * 1000, 2)

        # 5. Compute provisional search quality indicator based on top match
        quality_meta: RetrievalQuality | None = None
        if results:
            top_sim = results[0].similarity
            if top_sim >= self.settings.quality_high_threshold:
                qual = "high_similarity"
            elif top_sim >= self.settings.quality_medium_threshold:
                qual = "medium_similarity"
            else:
                qual = "low_similarity"
            quality_meta = RetrievalQuality(top_similarity=top_sim, quality=qual)

        timing = RetrievalTiming(
            validation_ms=validation_ms,
            embedding_ms=embedding_ms,
            vector_search_ms=vector_search_ms,
            total_ms=total_ms,
        )

        logger.info(
            "Retrieval completed for '%s' in %.2f ms (val: %.1fms, emb: %.1fms, search: %.1fms). Found %d matches.",
            filename,
            total_ms,
            validation_ms,
            embedding_ms,
            vector_search_ms,
            len(results),
        )

        return RetrievalResponse(
            query=QueryInfo(filename=filename),
            mode=mode,  # type: ignore[arg-type]
            category=category,
            results=results,
            result_count=len(results),
            processing_time_ms=total_ms,
            timing=timing,
            quality_meta=quality_meta,
        )


def get_retrieval_service() -> RetrievalService:
    """Return RetrievalService instance (freshly resolving dependencies)."""
    return RetrievalService()
