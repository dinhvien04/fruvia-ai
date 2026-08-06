"""
DINOv2 image feature encoder for image retrieval.

Loads facebook/dinov2-base and extracts 768-dimensional L2-normalized embeddings
using the CLS token output.
"""

from __future__ import annotations

import os
from typing import Any

import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModel

from app.core.config import Settings, get_settings
from app.core.exceptions import ImageEncodingError, ModelNotLoadedError
from app.core.logging import get_logger

logger = get_logger(__name__)

EXPECTED_VECTOR_SIZE = 768


class ImageEncoder:
    """
    DINOv2 Image Encoder for generating 768-dimensional image embeddings.

    Loads the model once at initialization using configured model name & revision,
    determines hardware device (CUDA if available, else CPU), and executes fast
    inference in torch.inference_mode.
    """

    def __init__(
        self,
        model_name: str | None = None,
        revision: str | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.model_name = model_name or self.settings.dinov2_model_name
        self.revision = revision or self.settings.dinov2_revision
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.processor: Any = None
        self.model: Any = None
        self.is_loaded: bool = False

    def load_model(self) -> None:
        """Load DINOv2 processor and model onto the configured device."""
        if self.is_loaded:
            logger.info("DINOv2 ImageEncoder model is already loaded.")
            return

        if self.settings.hf_home:
            os.environ["HF_HOME"] = str(self.settings.hf_home)

        logger.info(
            "Loading DINOv2 model '%s' (revision='%s') on device '%s'...",
            self.model_name,
            self.revision,
            self.device,
        )
        try:
            self.processor = AutoImageProcessor.from_pretrained(
                self.model_name, revision=self.revision
            )
            model = AutoModel.from_pretrained(self.model_name, revision=self.revision)
            model.to(self.device)
            model.eval()
            self.model = model
            self.is_loaded = True
            logger.info("DINOv2 ImageEncoder loaded successfully.")
        except Exception as e:
            logger.error("Failed to load DINOv2 model '%s': %s", self.model_name, e)
            self.is_loaded = False
            raise ModelNotLoadedError(
                message="Failed to load DINOv2 image encoder.",
                detail=str(e),
            ) from e

    def encode_image(self, image: Image.Image) -> list[float]:
        """
        Encode a PIL Image into a 768-dimensional L2-normalized float list.

        Parameters
        ----------
        image : PIL.Image.Image
            Input image. Converted to RGB before feature extraction.

        Returns
        -------
        list[float]
            768-dimensional L2-normalized embedding vector.
        """
        if not self.is_loaded or self.model is None or self.processor is None:
            raise ModelNotLoadedError(
                message="DINOv2 model is not loaded.",
                detail="encode_image called before load_model() succeeded.",
            )

        try:
            # 1. Convert to RGB
            rgb_image = image.convert("RGB")

            # 2. Preprocess & inference in torch.inference_mode
            with torch.inference_mode():
                inputs = self.processor(images=rgb_image, return_tensors="pt")
                if hasattr(inputs, "to"):
                    inputs = inputs.to(self.device)
                else:
                    inputs = {
                        k: v.to(self.device) if hasattr(v, "to") else v for k, v in inputs.items()
                    }
                outputs = self.model(**inputs)

                # 3. Extract CLS token (index 0)
                cls_token = outputs.last_hidden_state[:, 0, :].to(dtype=torch.float32)

                # 4. L2 Normalize
                normalized_tensor = torch.nn.functional.normalize(cls_token, p=2, dim=1)

                # 5. Check finite numbers (no NaN or Inf)
                if not torch.all(torch.isfinite(normalized_tensor)):
                    raise ImageEncodingError(
                        message="Failed to extract features from the image.",
                        detail="Generated embedding contains non-finite values (NaN or Inf).",
                    )

                # 6. Convert to python list
                vector = normalized_tensor.squeeze(0).cpu().tolist()

            if len(vector) != EXPECTED_VECTOR_SIZE:
                raise ImageEncodingError(
                    message="Failed to extract features from the image.",
                    detail=f"Expected vector size {EXPECTED_VECTOR_SIZE}, got {len(vector)}.",
                )

            return vector

        except (ModelNotLoadedError, ImageEncodingError):
            raise
        except Exception as e:
            logger.error("Error during image encoding: %s", e, exc_info=True)
            raise ImageEncodingError(
                message="Failed to extract features from the image.",
                detail=str(e),
            ) from e


_encoder_instance: ImageEncoder | None = None


def get_image_encoder() -> ImageEncoder:
    """Return singleton ImageEncoder instance."""
    global _encoder_instance
    if _encoder_instance is None:
        _encoder_instance = ImageEncoder()
    return _encoder_instance
