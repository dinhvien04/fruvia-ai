"""
Unit tests for file utilities — YAML loading, stable UUID, class mapping.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.utils.file_utils import (
    generate_stable_uuid,
    load_class_list,
    load_class_mapping,
    load_yaml_config,
)

pytestmark = pytest.mark.unit


class TestGenerateStableUuid:
    """Tests for deterministic UUID generation."""

    def test_same_inputs_same_output(self) -> None:
        """Same inputs must always produce the same UUID."""
        u1 = generate_stable_uuid("dinov2", "img_001", "v1")
        u2 = generate_stable_uuid("dinov2", "img_001", "v1")
        assert u1 == u2

    def test_different_inputs_different_output(self) -> None:
        """Different inputs must produce different UUIDs."""
        u1 = generate_stable_uuid("dinov2", "img_001", "v1")
        u2 = generate_stable_uuid("dinov2", "img_002", "v1")
        assert u1 != u2

    def test_different_namespace_different_output(self) -> None:
        u1 = generate_stable_uuid("dinov2", "img_001", "v1")
        u2 = generate_stable_uuid("resnet50", "img_001", "v1")
        assert u1 != u2

    def test_uuid_format(self) -> None:
        """Must return a valid UUID string."""
        u = generate_stable_uuid("model", "image", "version")
        import uuid

        parsed = uuid.UUID(u)
        assert parsed.version == 5


class TestLoadClassList:
    """Tests for loading classes.yaml."""

    def test_load_valid(self, classes_yaml: Path) -> None:
        result = load_class_list(classes_yaml)
        assert isinstance(result, list)
        assert "apple" in result
        assert "banana" in result
        assert len(result) == 5

    def test_missing_file_raises(self, tmp_dir: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_class_list(tmp_dir / "nonexistent.yaml")


class TestLoadClassMapping:
    """Tests for loading class_mapping.yaml."""

    def test_load_valid(self, class_mapping_yaml: Path) -> None:
        result = load_class_mapping(class_mapping_yaml)
        assert isinstance(result, dict)
        assert result["Apple Braeburn"] == "apple"
        assert result["Banana"] == "banana"
        assert result["Banana Red"] == "banana"

    def test_many_to_one_mapping(self, class_mapping_yaml: Path) -> None:
        """Multiple original classes can map to a single target."""
        mapping = load_class_mapping(class_mapping_yaml)
        apple_sources = [k for k, v in mapping.items() if v == "apple"]
        assert len(apple_sources) >= 2


class TestLoadYamlConfig:
    """Tests for the generic YAML loader."""

    def test_load_valid_yaml(self, training_config_yaml: Path) -> None:
        data = load_yaml_config(training_config_yaml)
        assert "preprocessing" in data
        assert data["random_seed"] == 42

    def test_missing_file_raises(self, tmp_dir: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_yaml_config(tmp_dir / "nope.yaml")
