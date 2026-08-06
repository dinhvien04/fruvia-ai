"""
Unit tests for preprocessing configuration loading.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ml.preprocessing import load_preprocessing_config

pytestmark = pytest.mark.unit


class TestLoadPreprocessingConfig:
    """Tests for loading preprocessing.json."""

    def test_valid_config(self, preprocessing_config: Path) -> None:
        config = load_preprocessing_config(preprocessing_config)
        assert config["image_size"] == 224
        assert len(config["mean"]) == 3
        assert len(config["std"]) == 3
        assert all(isinstance(v, float) for v in config["mean"])

    def test_missing_key_raises(self, tmp_dir: Path) -> None:
        path = tmp_dir / "bad_preprocessing.json"
        with open(path, "w") as f:
            json.dump({"image_size": 224}, f)  # missing mean and std
        with pytest.raises(ValueError, match="missing keys"):
            load_preprocessing_config(path)

    def test_complete_config_has_all_keys(self, preprocessing_config: Path) -> None:
        config = load_preprocessing_config(preprocessing_config)
        assert "image_size" in config
        assert "mean" in config
        assert "std" in config


class TestPreprocessingValues:
    """Tests that preprocessing values are within expected ranges."""

    def test_imagenet_mean_range(self, preprocessing_config: Path) -> None:
        config = load_preprocessing_config(preprocessing_config)
        for val in config["mean"]:
            assert 0.0 <= val <= 1.0, f"Mean value {val} out of [0, 1] range"

    def test_imagenet_std_range(self, preprocessing_config: Path) -> None:
        config = load_preprocessing_config(preprocessing_config)
        for val in config["std"]:
            assert 0.0 < val <= 1.0, f"Std value {val} out of (0, 1] range"
