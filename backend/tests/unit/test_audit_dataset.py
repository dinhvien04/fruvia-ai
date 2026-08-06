"""
Unit tests for the dataset audit script.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.audit_dataset import (
    compute_sha256,
    discover_classes,
    find_duplicates,
    validate_image,
)

pytestmark = pytest.mark.unit


class TestComputeSha256:
    """Tests for SHA-256 hashing."""

    def test_deterministic(self, tmp_dir: Path) -> None:
        path = tmp_dir / "test.bin"
        path.write_bytes(b"hello world")
        h1 = compute_sha256(path)
        h2 = compute_sha256(path)
        assert h1 == h2
        assert len(h1) == 64  # hex digest length

    def test_different_content_different_hash(self, tmp_dir: Path) -> None:
        p1 = tmp_dir / "a.bin"
        p2 = tmp_dir / "b.bin"
        p1.write_bytes(b"hello")
        p2.write_bytes(b"world")
        assert compute_sha256(p1) != compute_sha256(p2)


class TestValidateImage:
    """Tests for Pillow-based image validation."""

    def test_valid_image(self, tmp_dir: Path, sample_rgb_image) -> None:
        path = tmp_dir / "valid.jpg"
        sample_rgb_image.save(path, format="JPEG")
        is_valid, size = validate_image(path)
        assert is_valid is True
        assert size == (100, 100)

    def test_invalid_file(self, tmp_dir: Path) -> None:
        path = tmp_dir / "corrupt.jpg"
        path.write_bytes(b"not an image at all")
        is_valid, size = validate_image(path)
        assert is_valid is False
        assert size is None


class TestDiscoverClasses:
    """Tests for class folder discovery."""

    def test_discovers_classes_in_splits(self, sample_dataset: Path) -> None:
        classes = discover_classes(sample_dataset)
        assert "Apple Braeburn" in classes
        assert "Banana" in classes
        assert "Mango" in classes

    def test_empty_dir(self, tmp_dir: Path) -> None:
        classes = discover_classes(tmp_dir / "nonexistent")
        assert classes == []


class TestFindDuplicates:
    """Tests for SHA-256 duplicate detection."""

    def test_no_duplicates(self) -> None:
        records = [
            {"sha256": "aaa", "relative_path": "a.jpg"},
            {"sha256": "bbb", "relative_path": "b.jpg"},
        ]
        dups = find_duplicates(records)
        assert len(dups) == 0

    def test_finds_duplicates(self) -> None:
        records = [
            {"sha256": "aaa", "relative_path": "a.jpg"},
            {"sha256": "aaa", "relative_path": "a_copy.jpg"},
            {"sha256": "bbb", "relative_path": "b.jpg"},
        ]
        dups = find_duplicates(records)
        assert len(dups) == 1
        assert "aaa" in dups
        assert len(dups["aaa"]) == 2
