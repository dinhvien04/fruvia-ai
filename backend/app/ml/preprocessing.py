"""
Image preprocessing for classification inference.

This module reads the preprocessing config exported by the training pipeline
(models/classifier/preprocessing.json) and applies the exact same transforms.
No independent preprocessing definitions — single source of truth.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image


def load_preprocessing_config(config_path: Path) -> Dict[str, Any]:
    """
    Load preprocessing parameters from the exported JSON.

    Expected keys:
    - image_size: int
    - mean: [float, float, float]
    - std: [float, float, float]
    - interpolation: str
    - color_mode: str
    """
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    required_keys = {"image_size", "mean", "std"}
    missing = required_keys - set(config.keys())
    if missing:
        raise ValueError(
            f"Preprocessing config missing keys: {missing}. "
            f"Expected at least: {required_keys}"
        )
    return config


def get_preprocessing_transforms(config: Dict[str, Any]) -> Any:
    """
    Build a torchvision transform pipeline from preprocessing config.

    This is called once at startup. The returned transform is applied
    to every input image.

    Returns a torchvision.transforms.Compose object.
    """
    # Import here to avoid import errors when torch is not installed
    # (e.g., during unit tests that mock this module)
    import torchvision.transforms as T

    image_size = config["image_size"]
    mean = config["mean"]
    std = config["std"]

    transforms = T.Compose([
        T.Resize((image_size, image_size), interpolation=T.InterpolationMode.BILINEAR),
        T.ToTensor(),
        T.Normalize(mean=mean, std=std),
    ])
    return transforms


def preprocess_image(
    image: Image.Image,
    config: Dict[str, Any],
) -> Any:
    """
    Preprocess a PIL Image for model inference.

    Parameters
    ----------
    image : PIL.Image.Image
        Input image (must be RGB).
    config : dict
        Preprocessing config from load_preprocessing_config().

    Returns
    -------
    torch.Tensor
        Preprocessed tensor with shape (1, 3, H, W), ready for model input.
    """
    import torch

    transform = get_preprocessing_transforms(config)
    tensor = transform(image)

    # Add batch dimension
    if tensor.dim() == 3:
        tensor = tensor.unsqueeze(0)

    return tensor
