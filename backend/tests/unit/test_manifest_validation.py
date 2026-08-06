"""
Unit tests for manifest validation script.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.validate_manifest import validate_manifest

pytestmark = pytest.mark.unit


class TestValidateManifest:
    """Tests for manifest CSV validation."""

    def test_valid_manifest_passes(self, sample_manifest_csv: Path, classes_yaml: Path) -> None:
        report = validate_manifest(
            manifest_path=sample_manifest_csv,
            classes_path=classes_yaml,
        )
        assert report["is_valid"] is True
        assert report["total_rows"] == 2
        assert len(report["errors"]) == 0

    def test_detects_required_columns(self, sample_manifest_csv: Path) -> None:
        report = validate_manifest(manifest_path=sample_manifest_csv)
        # All required columns should be present in the sample
        assert len(report["columns_missing"]) == 0

    def test_counts_splits(self, sample_manifest_csv: Path) -> None:
        report = validate_manifest(manifest_path=sample_manifest_csv)
        assert "train" in report["split_counts"]
        assert "validation" in report["split_counts"]
