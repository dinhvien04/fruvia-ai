"""
Unit tests for configuration loading and validation.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.config import Settings, load_class_names

pytestmark = pytest.mark.unit


class TestSettings:
    """Tests for the Settings configuration class."""

    def test_default_values(self) -> None:
        """Settings should have sensible defaults without any env vars."""
        with patch.dict(os.environ, {}, clear=True):
            s = Settings(_env_file=None)
        assert s.app_env == "development"
        assert s.app_port == 8000
        assert s.classification_threshold == 0.65
        assert s.max_upload_mb == 10
        assert s.qdrant_collection == "fruvia_fruits360_original_dinov2_base_v1"
        assert s.log_level == "INFO"

    def test_max_upload_bytes(self) -> None:
        with patch.dict(os.environ, {"MAX_UPLOAD_MB": "5"}, clear=True):
            s = Settings()
        assert s.max_upload_bytes == 5 * 1024 * 1024

    def test_cors_origin_list_single(self) -> None:
        with patch.dict(os.environ, {"CORS_ORIGINS": "http://localhost:3000"}, clear=True):
            s = Settings()
        assert s.cors_origin_list == ["http://localhost:3000"]

    def test_cors_origin_list_multiple(self) -> None:
        with patch.dict(
            os.environ,
            {"CORS_ORIGINS": "http://localhost:3000,http://localhost:8080"},
            clear=True,
        ):
            s = Settings()
        assert s.cors_origin_list == ["http://localhost:3000", "http://localhost:8080"]

    def test_is_production(self) -> None:
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "production",
                "ALLOWED_HOSTS": "fruvia.ai,api.fruvia.ai",
                "CORS_ORIGINS": "https://fruvia.ai",
                "DINOV2_REVISION": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
                "QDRANT_URL": "https://qdrant.cloud:6333",
            },
            clear=True,
        ):
            s = Settings()
        assert s.is_production is True

    def test_is_not_production(self) -> None:
        with patch.dict(os.environ, {"APP_ENV": "development"}, clear=True):
            s = Settings()
        assert s.is_production is False

    def test_invalid_log_level_rejected(self) -> None:
        with (
            patch.dict(os.environ, {"LOG_LEVEL": "VERBOSE"}, clear=True),
            pytest.raises(ValueError, match="log_level must be one of"),
        ):
            Settings()

    def test_classification_threshold_bounds(self) -> None:
        with (
            patch.dict(os.environ, {"CLASSIFICATION_THRESHOLD": "1.5"}, clear=True),
            pytest.raises(ValueError),
        ):
            Settings()

    def test_threshold_from_env(self) -> None:
        with patch.dict(os.environ, {"CLASSIFICATION_THRESHOLD": "0.8"}, clear=True):
            s = Settings()
        assert s.classification_threshold == 0.8

    def test_production_dinov2_revision_validation(self) -> None:
        valid_sha = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "production",
                "ALLOWED_HOSTS": "fruvia.ai",
                "CORS_ORIGINS": "https://fruvia.ai",
                "DINOV2_REVISION": valid_sha,
                "QDRANT_URL": "https://qdrant.cloud:6333",
            },
            clear=True,
        ):
            s = Settings()
            assert s.dinov2_revision == valid_sha

        with (
            patch.dict(
                os.environ,
                {
                    "APP_ENV": "production",
                    "ALLOWED_HOSTS": "fruvia.ai",
                    "CORS_ORIGINS": "https://fruvia.ai",
                    "DINOV2_REVISION": "main",
                    "QDRANT_URL": "https://qdrant.cloud:6333",
                },
                clear=True,
            ),
            pytest.raises(
                ValueError,
                match="DINOV2_REVISION must match exactly a 40-character hexadecimal commit SHA",
            ),
        ):
            Settings()

    def test_body_and_upload_limits_validation(self) -> None:
        with (
            patch.dict(
                os.environ,
                {"MAX_UPLOAD_MB": "15", "MAX_REQUEST_BODY_MB": "10"},
                clear=True,
            ),
            pytest.raises(ValueError, match="MAX_REQUEST_BODY_MB .* must be >= MAX_UPLOAD_MB"),
        ):
            Settings()

    def test_migration_key_distinction(self) -> None:
        with patch.dict(
            os.environ,
            {
                "QDRANT_API_KEY": "read-only-key",
                "QDRANT_MIGRATION_API_KEY": "admin-key",
            },
            clear=True,
        ):
            s = Settings()
            assert s.qdrant_api_key == "read-only-key"
            assert s.qdrant_migration_api_key == "admin-key"


class TestLoadClassNames:
    """Tests for load_class_names helper."""

    def test_load_list_format(self, tmp_dir: Path) -> None:
        path = tmp_dir / "classes.json"
        with open(path, "w") as f:
            json.dump(["apple", "banana", "mango"], f)
        result = load_class_names(path)
        assert result == ["apple", "banana", "mango"]

    def test_load_dict_format(self, tmp_dir: Path) -> None:
        path = tmp_dir / "classes.json"
        with open(path, "w") as f:
            json.dump({"classes": ["orange", "pear"]}, f)
        result = load_class_names(path)
        assert result == ["orange", "pear"]

    def test_invalid_format_raises(self, tmp_dir: Path) -> None:
        path = tmp_dir / "classes.json"
        with open(path, "w") as f:
            json.dump({"items": ["x"]}, f)
        with pytest.raises(ValueError, match="Unexpected class_names format"):
            load_class_names(path)
