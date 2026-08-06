"""
Business logic service for fruit image retrieval via vector search.
"""

from __future__ import annotations

import time

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.ml.image_encoder import ImageEncoder, get_image_encoder
from app.repositories.qdrant_repository import QdrantRepository, get_qdrant_repository
from app.schemas.retrieval import QueryInfo, RetrievalResponse
from app.utils.image_validation import validate_upload

logger = get_logger(__name__)


class RetrievalService:
    """
    Service orchestrating image validation, DINOv2 feature extraction,
    and Qdrant Cloud vector search.
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

        Returns
        -------
        RetrievalResponse
            Retrieval query metadata, results with similarity scores, and execution timing.
        """
        start_time = time.perf_counter()

        logger.info(
            "Processing retrieval request for file '%s' (bytes=%d, top_k=%d)...",
            filename,
            len(file_bytes),
            top_k,
        )

        # 1. Validate image format, size, and integrity
        pil_image, _ = validate_upload(
            data=file_bytes,
            filename=filename,
            max_bytes=self.settings.max_upload_bytes,
        )

        # 2. Extract 768-dim L2-normalized feature vector using DINOv2
        query_vector = self.encoder.encode_image(pil_image)

        # 3. Perform cosine similarity vector search in Qdrant Cloud
        results = self.qdrant_repo.query_similar(vector=query_vector, top_k=top_k)

        # 4. Calculate execution time in milliseconds
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        logger.info(
            "Retrieval completed for '%s' in %.2f ms. Found %d matches.",
            filename,
            elapsed_ms,
            len(results),
        )

        return RetrievalResponse(
            query=QueryInfo(filename=filename),
            results=results,
            result_count=len(results),
            processing_time_ms=elapsed_ms,
        )


def get_retrieval_service() -> RetrievalService:
    """Return RetrievalService instance (freshly resolving dependencies)."""
    return RetrievalService()
