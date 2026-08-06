"""
Unit tests for ImageEncoder (DINOv2 embedding generator).
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

import PIL.Image
import pytest
import torch

from app.core.exceptions import ImageEncodingError, ModelNotLoadedError
from app.ml.image_encoder import ImageEncoder

pytestmark = pytest.mark.unit


class TestImageEncoder:
    """Unit tests for ImageEncoder class."""

    def test_not_loaded_raises_exception(self, sample_rgb_image: PIL.Image.Image) -> None:
        """Calling encode_image before load_model should raise ModelNotLoadedError."""
        encoder = ImageEncoder()
        with pytest.raises(ModelNotLoadedError, match="not loaded"):
            encoder.encode_image(sample_rgb_image)

    @patch("app.ml.image_encoder.AutoModel")
    @patch("app.ml.image_encoder.AutoImageProcessor")
    def test_vector_size_and_l2_norm(
        self,
        mock_processor_cls: MagicMock,
        mock_model_cls: MagicMock,
        sample_rgb_image: PIL.Image.Image,
    ) -> None:
        """Vector size must be 768 and L2 norm must be approximately 1.0."""
        # Setup mock processor
        mock_processor = MagicMock()
        mock_processor.return_value = {"pixel_values": torch.zeros((1, 3, 224, 224))}
        mock_processor_cls.from_pretrained.return_value = mock_processor

        # Setup mock model with 768-dim output
        mock_model = MagicMock()
        fake_hidden = torch.randn(1, 197, 768)  # DINOv2 output shape (batch, tokens, dim)
        mock_outputs = MagicMock()
        mock_outputs.last_hidden_state = fake_hidden
        mock_model.return_value = mock_outputs
        mock_model_cls.from_pretrained.return_value = mock_model

        encoder = ImageEncoder()
        encoder.load_model()

        vector = encoder.encode_image(sample_rgb_image)

        assert isinstance(vector, list)
        assert len(vector) == 768
        assert all(isinstance(x, float) for x in vector)

        # L2 norm check
        l2_norm = math.sqrt(sum(x * x for x in vector))
        assert math.isclose(l2_norm, 1.0, abs_tol=1e-4)

    @patch("app.ml.image_encoder.AutoModel")
    @patch("app.ml.image_encoder.AutoImageProcessor")
    def test_non_finite_values_raise_exception(
        self,
        mock_processor_cls: MagicMock,
        mock_model_cls: MagicMock,
        sample_rgb_image: PIL.Image.Image,
    ) -> None:
        """Non-finite values (NaN / Inf) in embedding output must raise ImageEncodingError."""
        mock_processor = MagicMock()
        mock_processor.return_value = {"pixel_values": torch.zeros((1, 3, 224, 224))}
        mock_processor_cls.from_pretrained.return_value = mock_processor

        # Inject NaN into model output
        mock_model = MagicMock()
        fake_hidden = torch.full((1, 197, 768), float("nan"))
        mock_outputs = MagicMock()
        mock_outputs.last_hidden_state = fake_hidden
        mock_model.return_value = mock_outputs
        mock_model_cls.from_pretrained.return_value = mock_model

        encoder = ImageEncoder()
        encoder.load_model()

        with pytest.raises(ImageEncodingError, match="non-finite|Failed to extract features"):
            encoder.encode_image(sample_rgb_image)
