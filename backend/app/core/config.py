"""
Fruvia AI application settings.

All configuration is loaded from environment variables via Pydantic Settings.
No secret is ever hardcoded — see .env.example for the full list.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def find_project_root() -> Path:
    """Find repository root by looking for configs/ directory or pyproject.toml."""
    curr = Path(__file__).resolve().parent
    for p in [curr] + list(curr.parents):
        if (p / "configs").exists() or (p / "pyproject.toml").exists():
            return p
    return Path.cwd()


PROJECT_ROOT = find_project_root()


class Settings(BaseSettings):
    """Central configuration read from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    app_env: str = Field(default="development", description="development | staging | production")
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)
    app_version: str = Field(default="0.1.0")

    # --- DINOv2 Embedding Model ---
    dinov2_model_name: str = Field(
        default="facebook/dinov2-base", description="Hugging Face model repository ID"
    )
    dinov2_revision: str = Field(
        default="main", description="Pinned commit hash or revision tag for DINOv2 model"
    )
    hf_home: Path | None = Field(
        default=None, description="Optional custom directory for Hugging Face cache"
    )

    # --- Classification Model ---
    model_path: Path = Field(default=Path("models/classifier/model.pth"))
    class_names_path: Path = Field(default=Path("models/classifier/class_names.json"))
    model_config_path: Path = Field(default=Path("models/classifier/model_config.json"))
    preprocessing_config_path: Path = Field(default=Path("models/classifier/preprocessing.json"))

    # --- Classification Behavior ---
    classification_threshold: float = Field(
        default=0.65, ge=0.0, le=1.0, description="Minimum confidence to accept a prediction"
    )

    # --- Qdrant ---
    qdrant_url: str | None = Field(default=None, description="Qdrant Cloud endpoint URL")
    qdrant_api_key: str | None = Field(default=None, description="Qdrant Cloud API key")
    qdrant_collection: str = Field(default="fruvia_fruits360_original_dinov2_base_v1")
    qdrant_timeout: int = Field(default=10, description="Qdrant request timeout in seconds")

    # --- Search Behavior ---
    class_search_candidate_multiplier: int = Field(
        default=4,
        ge=2,
        le=10,
        description="Multiplier for candidate pool size in class search mode",
    )
    class_search_min_candidates: int = Field(
        default=30, ge=10, le=200, description="Minimum candidate pool size for class search mode"
    )
    class_search_max_candidates: int = Field(
        default=300,
        ge=50,
        le=1000,
        description="Maximum candidate cap for iterative pool expansion",
    )

    # --- Rate Limiting & Concurrency ---
    rate_limit_per_minute: int = Field(
        default=60, ge=1, description="Max requests per minute per IP"
    )
    max_concurrent_inferences: int = Field(
        default=4, ge=1, description="Max concurrent ML model inferences"
    )

    # --- Upload ---
    max_upload_mb: int = Field(default=10, ge=1, le=50)
    max_image_pixels: int = Field(
        default=25_000_000, description="Maximum total pixel count to prevent decompression bombs"
    )
    max_image_width: int = Field(default=5000, description="Maximum image width in pixels")
    max_image_height: int = Field(default=5000, description="Maximum image height in pixels")
    class_mapping_path: Path = Field(
        default=PROJECT_ROOT / "configs" / "class_mapping.yaml",
        description="Path to original->canonical class mapping YAML",
    )
    taxonomy_path: Path = Field(
        default=PROJECT_ROOT / "configs" / "taxonomy.yaml",
        description="Path to taxonomy YAML file",
    )

    # --- CORS ---
    cors_origins: str = Field(default="http://localhost:3000")

    # --- Logging ---
    log_level: str = Field(default="INFO")

    # --- Derived properties ---

    @property
    def max_upload_bytes(self) -> int:
        """Maximum upload size in bytes."""
        return self.max_upload_mb * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}, got '{v}'")
        return upper


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return a cached Settings instance.

    Call this instead of constructing Settings() directly so the
    environment is read only once.
    """
    return Settings()


def load_class_names(path: Path) -> list[str]:
    """Load the ordered list of class names from a JSON file."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "classes" in data:
        return data["classes"]
    raise ValueError(f"Unexpected class_names format in {path}")
