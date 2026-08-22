"""
BGE-M3 Dense Text Encoder for semantic knowledge retrieval.

Loads BAAI/bge-m3 via sentence-transformers and extracts 1024-dimensional
L2-normalized dense embeddings for semantic search in Qdrant Cloud.
"""

from __future__ import annotations

import math
import os
from typing import Any

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    KnowledgeEncoderUnavailableError,
    KnowledgeEncodingError,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

EXPECTED_KNOWLEDGE_VECTOR_SIZE = 1024


class TextEncoder:
    """
    BGE-M3 Text Encoder for generating 1024-dimensional dense text embeddings.

    Loads the model once at initialization when knowledge retrieval is enabled,
    configures device (CUDA, CPU, or Auto), and produces normalized float vectors.
    """

    def __init__(
        self,
        model_name: str | None = None,
        revision: str | None = None,
        device: str | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.model_name = model_name or self.settings.knowledge_model_name
        self.revision = revision or self.settings.knowledge_model_revision
        self.device_setting = (device or self.settings.knowledge_device).lower().strip()
        self.device = self._resolve_device(self.device_setting)
        self.model: Any = None
        self.is_loaded: bool = False

    @staticmethod
    def _resolve_device(device_setting: str) -> str:
        """Resolve device string: 'auto' -> cuda if available else cpu, 'cuda', 'cpu'."""
        if device_setting == "cuda":
            if not torch.cuda.is_available():
                logger.warning(
                    "CUDA requested for TextEncoder but not available. Falling back to CPU."
                )
                return "cpu"
            return "cuda"
        if device_setting == "cpu":
            return "cpu"
        # "auto" or default
        return "cuda" if torch.cuda.is_available() else "cpu"

    def load_model(self) -> None:
        """Load BGE-M3 model onto the configured device."""
        if self.is_loaded:
            logger.info("BGE-M3 TextEncoder model is already loaded.")
            return

        if self.settings.hf_home:
            os.environ["HF_HOME"] = str(self.settings.hf_home)

        logger.info(
            "Loading BGE-M3 TextEncoder model '%s' (revision='%s') on device '%s'...",
            self.model_name,
            self.revision,
            self.device,
        )
        try:
            # SentenceTransformer accepts revision argument
            model_kwargs: dict[str, Any] = {}
            if self.revision and self.revision != "main":
                model_kwargs["revision"] = self.revision

            self.model = SentenceTransformer(
                self.model_name,
                device=self.device,
                **model_kwargs,
            )
            self.is_loaded = True
            logger.info("BGE-M3 TextEncoder loaded successfully.")
        except Exception as e:
            logger.error("Failed to load BGE-M3 model '%s': %s", self.model_name, e)
            self.is_loaded = False
            raise KnowledgeEncoderUnavailableError(
                message="Failed to load BGE-M3 text encoder.",
                detail=str(e),
            ) from e

    def encode_text(self, text: str) -> list[float]:
        """
        Encode a single text string into a 1024-dimensional L2-normalized float list.

        Parameters
        ----------
        text : str
            Query text string.

        Returns
        -------
        list[float]
            1024-dimensional L2-normalized embedding vector.
        """
        if not self.is_loaded or self.model is None:
            raise KnowledgeEncoderUnavailableError(
                message="BGE-M3 text encoder is not loaded.",
                detail="encode_text called before load_model() succeeded.",
            )

        clean_text = text.strip()
        if not clean_text:
            raise KnowledgeEncodingError(
                message="Cannot encode empty text.",
                detail="Text query was empty or contained only whitespace.",
            )

        try:
            # Generate dense embedding with L2 normalization
            embedding = self.model.encode(
                clean_text,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )

            # Ensure 1D numpy array
            if isinstance(embedding, np.ndarray):
                if embedding.ndim > 1:
                    embedding = embedding.flatten()
                vector = [float(x) for x in embedding]
            elif isinstance(embedding, list):
                vector = [float(x) for x in embedding]
            elif hasattr(embedding, "tolist"):
                vector = [float(x) for x in embedding.tolist()]
            else:
                raise KnowledgeEncodingError(
                    message="Unexpected embedding return type from SentenceTransformer.",
                    detail=f"Returned type: {type(embedding)}",
                )

            # Verify dimensionality
            if len(vector) != EXPECTED_KNOWLEDGE_VECTOR_SIZE:
                raise KnowledgeEncodingError(
                    message="Text encoder generated an embedding of invalid dimension.",
                    detail=f"Expected {EXPECTED_KNOWLEDGE_VECTOR_SIZE}D, got {len(vector)}D.",
                )

            # Verify numerical sanity (finite, no NaN or Inf)
            if not all(math.isfinite(x) for x in vector):
                raise KnowledgeEncodingError(
                    message="Text embedding contains non-finite numbers (NaN or Inf).",
                    detail="Generated vector contained non-finite values.",
                )

            return vector

        except (KnowledgeEncoderUnavailableError, KnowledgeEncodingError):
            raise
        except Exception as e:
            logger.error("Error during text encoding: %s", e, exc_info=True)
            raise KnowledgeEncodingError(
                message="Failed to generate embeddings for the text query.",
                detail=str(e),
            ) from e


_text_encoder_instance: TextEncoder | None = None


def get_text_encoder() -> TextEncoder:
    """Return singleton TextEncoder instance."""
    global _text_encoder_instance
    if _text_encoder_instance is None:
        _text_encoder_instance = TextEncoder()
    return _text_encoder_instance
