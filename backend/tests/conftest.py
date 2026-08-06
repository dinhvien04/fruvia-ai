"""
Shared test fixtures for the Fruvia AI test suite.
"""

from __future__ import annotations

import io
import json
import os
import struct
import tempfile
from pathlib import Path
from typing import Dict

import pytest
import yaml
from PIL import Image


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory."""
    return tmp_path


@pytest.fixture
def sample_rgb_image() -> Image.Image:
    """Create a small valid RGB image in memory."""
    return Image.new("RGB", (100, 100), color=(255, 128, 0))


@pytest.fixture
def sample_rgba_image() -> Image.Image:
    """Create a small RGBA image (needs conversion to RGB)."""
    return Image.new("RGBA", (80, 80), color=(255, 128, 0, 200))


@pytest.fixture
def sample_jpg_bytes(sample_rgb_image: Image.Image) -> bytes:
    """JPEG bytes from a valid image."""
    buf = io.BytesIO()
    sample_rgb_image.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def sample_png_bytes(sample_rgb_image: Image.Image) -> bytes:
    """PNG bytes from a valid image."""
    buf = io.BytesIO()
    sample_rgb_image.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def corrupt_image_bytes() -> bytes:
    """Bytes that look like they might be an image but are corrupt."""
    return b"\xff\xd8\xff\xe0" + b"\x00" * 100 + b"not an image at all"


@pytest.fixture
def non_image_bytes() -> bytes:
    """Bytes that are clearly not an image (e.g. a text file)."""
    return b"Hello, this is a plain text file, not an image."


@pytest.fixture
def oversized_bytes() -> bytes:
    """Bytes exceeding a typical upload limit (11 MB)."""
    return b"\x00" * (11 * 1024 * 1024)


@pytest.fixture
def classes_yaml(tmp_dir: Path) -> Path:
    """Create a temporary classes.yaml."""
    content = {
        "version": "1.0",
        "classes": ["apple", "banana", "mango", "orange", "strawberry"],
    }
    path = tmp_dir / "classes.yaml"
    with open(path, "w") as f:
        yaml.dump(content, f)
    return path


@pytest.fixture
def class_mapping_yaml(tmp_dir: Path) -> Path:
    """Create a temporary class_mapping.yaml."""
    content = {
        "version": "1.0",
        "class_mapping": {
            "Apple Braeburn": "apple",
            "Apple Golden 1": "apple",
            "Banana": "banana",
            "Banana Red": "banana",
            "Mango": "mango",
            "Orange": "orange",
            "Strawberry": "strawberry",
        },
    }
    path = tmp_dir / "class_mapping.yaml"
    with open(path, "w") as f:
        yaml.dump(content, f)
    return path


@pytest.fixture
def training_config_yaml(tmp_dir: Path) -> Path:
    """Create a temporary training.yaml with preprocessing section."""
    content = {
        "version": "1.0",
        "random_seed": 42,
        "preprocessing": {
            "image_size": 224,
            "mean": [0.485, 0.456, 0.406],
            "std": [0.229, 0.224, 0.225],
        },
        "convnext": {
            "model_name": "convnext_tiny",
        },
    }
    path = tmp_dir / "training.yaml"
    with open(path, "w") as f:
        yaml.dump(content, f)
    return path


@pytest.fixture
def preprocessing_config(tmp_dir: Path) -> Path:
    """Create a temporary preprocessing.json."""
    config = {
        "image_size": 224,
        "mean": [0.485, 0.456, 0.406],
        "std": [0.229, 0.224, 0.225],
        "interpolation": "bilinear",
        "color_mode": "RGB",
    }
    path = tmp_dir / "preprocessing.json"
    with open(path, "w") as f:
        json.dump(config, f)
    return path


@pytest.fixture
def sample_dataset(tmp_dir: Path) -> Path:
    """
    Create a small fake Fruits-360-like dataset on disk.

    Structure: data_dir/Training/<class>/img_xxx.jpg
    """
    data_dir = tmp_dir / "dataset"
    for split in ["Training", "Test"]:
        for cls in ["Apple Braeburn", "Banana", "Mango", "Orange"]:
            cls_dir = data_dir / split / cls
            cls_dir.mkdir(parents=True, exist_ok=True)
            for i in range(5):
                img = Image.new("RGB", (100, 100), color=(i * 50 % 256, 100, 200))
                img.save(cls_dir / f"img_{i:03d}.jpg", format="JPEG")
    return data_dir


@pytest.fixture
def sample_manifest_csv(tmp_dir: Path) -> Path:
    """Create a minimal valid manifest CSV."""
    import csv

    path = tmp_dir / "manifest.csv"
    fieldnames = [
        "image_id", "original_class", "target_class", "relative_path",
        "filename", "width", "height", "file_size", "sha256", "split",
        "source", "is_valid",
    ]
    rows = [
        {
            "image_id": "00000000-0000-0000-0000-000000000001",
            "original_class": "Apple Braeburn",
            "target_class": "apple",
            "relative_path": "Training/Apple Braeburn/img_000.jpg",
            "filename": "img_000.jpg",
            "width": "100",
            "height": "100",
            "file_size": "2048",
            "sha256": "a" * 64,
            "split": "train",
            "source": "Training",
            "is_valid": "True",
        },
        {
            "image_id": "00000000-0000-0000-0000-000000000002",
            "original_class": "Banana",
            "target_class": "banana",
            "relative_path": "Training/Banana/img_000.jpg",
            "filename": "img_000.jpg",
            "width": "100",
            "height": "100",
            "file_size": "2048",
            "sha256": "b" * 64,
            "split": "validation",
            "source": "Training",
            "is_valid": "True",
        },
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path
