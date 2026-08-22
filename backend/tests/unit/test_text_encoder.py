"""
Unit tests for BGE-M3 TextEncoder ML module.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.core.config import Settings
from app.core.exceptions import (
    KnowledgeEncoderUnavailableError,
    KnowledgeEncodingError,
)
from app.ml.text_encoder import TextEncoder, get_text_encoder


def test_text_encoder_singleton():
    """Verify get_text_encoder returns a singleton instance."""
    e1 = get_text_encoder()
    e2 = get_text_encoder()
    assert e1 is e2


def test_device_resolution():
    """Test device resolution for cpu, cuda, and auto."""
    settings = Settings(knowledge_device="cpu")
    encoder = TextEncoder(settings=settings)
    assert encoder.device == "cpu"

    with patch("torch.cuda.is_available", return_value=True):
        encoder_auto = TextEncoder(device="auto", settings=settings)
        assert encoder_auto.device == "cuda"

        encoder_cuda = TextEncoder(device="cuda", settings=settings)
        assert encoder_cuda.device == "cuda"

    with patch("torch.cuda.is_available", return_value=False):
        encoder_auto_cpu = TextEncoder(device="auto", settings=settings)
        assert encoder_auto_cpu.device == "cpu"

        # Fallback to cpu if cuda requested but not available
        encoder_cuda_fallback = TextEncoder(device="cuda", settings=settings)
        assert encoder_cuda_fallback.device == "cpu"


def test_load_model_success():
    """Test successful model loading using mocked SentenceTransformer."""
    mock_model = MagicMock()
    with patch("app.ml.text_encoder.SentenceTransformer", return_value=mock_model) as mock_st:
        encoder = TextEncoder(model_name="BAAI/bge-m3", revision="main")
        encoder.load_model()

        assert encoder.is_loaded is True
        assert encoder.model is mock_model
        mock_st.assert_called_once()


def test_load_model_failure():
    """Test exception handling during model load."""
    with patch(
        "app.ml.text_encoder.SentenceTransformer", side_effect=RuntimeError("Download failed")
    ):
        encoder = TextEncoder()
        with pytest.raises(KnowledgeEncoderUnavailableError) as exc_info:
            encoder.load_model()
        assert "Download failed" in str(exc_info.value.detail)
        assert encoder.is_loaded is False


def test_encode_text_not_loaded():
    """Test encode_text raises KnowledgeEncoderUnavailableError when not loaded."""
    encoder = TextEncoder()
    with pytest.raises(KnowledgeEncoderUnavailableError):
        encoder.encode_text("Apple nutrition facts")


def test_encode_text_empty():
    """Test encode_text rejects empty or whitespace-only queries."""
    encoder = TextEncoder()
    encoder.is_loaded = True
    encoder.model = MagicMock()

    with pytest.raises(KnowledgeEncodingError):
        encoder.encode_text("   ")


def test_encode_text_success():
    """Test successful text encoding returning 1024D normalized vector."""
    mock_model = MagicMock()
    fake_vec = np.ones(1024, dtype=np.float32) / np.sqrt(1024)
    mock_model.encode.return_value = fake_vec

    encoder = TextEncoder()
    encoder.is_loaded = True
    encoder.model = mock_model

    result = encoder.encode_text("What are the health benefits of dragonfruit?")
    assert len(result) == 1024
    assert isinstance(result[0], float)
    mock_model.encode.assert_called_once_with(
        "What are the health benefits of dragonfruit?",
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )


def test_encode_text_invalid_dimension():
    """Test encode_text fails when returned embedding is not 1024D."""
    mock_model = MagicMock()
    fake_vec = np.ones(768, dtype=np.float32)  # Wrong dimension (768 instead of 1024)
    mock_model.encode.return_value = fake_vec

    encoder = TextEncoder()
    encoder.is_loaded = True
    encoder.model = mock_model

    with pytest.raises(KnowledgeEncodingError) as exc_info:
        encoder.encode_text("Apple facts")
    assert "Expected 1024D, got 768D" in str(exc_info.value.detail)


def test_encode_text_non_finite_values():
    """Test encode_text detects and rejects NaN/Inf embeddings."""
    mock_model = MagicMock()
    fake_vec = np.ones(1024, dtype=np.float32)
    fake_vec[5] = float("nan")
    mock_model.encode.return_value = fake_vec

    encoder = TextEncoder()
    encoder.is_loaded = True
    encoder.model = mock_model

    with pytest.raises(KnowledgeEncodingError) as exc_info:
        encoder.encode_text("Apple facts")
    assert "non-finite" in str(exc_info.value.detail).lower()
