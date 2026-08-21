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
    allowed_hosts: str = Field(
        default="localhost,127.0.0.1,testserver,0.0.0.0",
        description="Comma-separated list of allowed Host header values for TrustedHostMiddleware",
    )

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

    # --- Qdrant & Gallery Collections ---
    qdrant_url: str | None = Field(default=None, description="Qdrant Cloud endpoint URL")
    qdrant_api_key: str | None = Field(
        default=None, description="Qdrant Cloud runtime API key (read-only recommended)"
    )
    qdrant_migration_api_key: str | None = Field(
        default=None, description="Dedicated admin/migration API key for Qdrant schema mutations"
    )
    qdrant_collection: str = Field(default="fruvia_fruits360_original_dinov2_base_v1")
    fruvia_gallery_collection: str | None = Field(
        default=None,
        description="Optional future unified gallery collection override (falls back to qdrant_collection)",
    )
    qdrant_timeout: int = Field(default=10, description="Qdrant request timeout in seconds")

    # --- Search Quality Thresholds (Provisional / Configurable) ---
    quality_high_threshold: float = Field(
        default=0.80,
        ge=0.0,
        le=1.0,
        description="Provisional cosine similarity threshold for 'high_similarity'",
    )
    quality_medium_threshold: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
        description="Provisional cosine similarity threshold for 'medium_similarity'",
    )

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
    trust_proxy_headers: bool = Field(
        default=False,
        description="Whether to trust X-Forwarded-For headers for client IP extraction (disabled by default to prevent spoofing)",
    )
    trusted_proxy_ips: str = Field(
        default="127.0.0.1,::1",
        description="Comma-separated list of trusted reverse proxy IP addresses allowed to forward client IPs",
    )
    native_filter_safe_collections: str = Field(
        default="fruvia_gallery_dinov2_base_v2",
        description="Comma-separated list of collection names guaranteed to have 100% payload indexing coverage for native filtering",
    )
    max_concurrent_inferences: int = Field(
        default=4, ge=1, description="Max concurrent ML model inferences"
    )

    # --- Upload & Request Body Limits ---
    max_upload_mb: int = Field(default=10, ge=1, le=50)
    max_request_body_mb: int = Field(
        default=12,
        ge=1,
        le=60,
        description="Maximum raw HTTP request body size in MB (must be >= max_upload_mb)",
    )
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

    # --- Security & Response Headers ---
    enable_hsts: bool = Field(
        default=False,
        description="Whether to send Strict-Transport-Security header (production HTTPS only)",
    )
    allowed_image_hosts: str = Field(
        default="",
        description="Comma-separated list of approved CDN/image hostnames for Content-Security-Policy img-src",
    )
    csp_connect_origins: str = Field(
        default="",
        description="Comma-separated list of additional API origins for Content-Security-Policy connect-src",
    )

    # --- Derived properties ---

    @property
    def allowed_host_list(self) -> list[str]:
        """Parse comma-separated allowed hosts into a list."""
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]

    @property
    def allowed_image_host_list(self) -> list[str]:
        """Parse comma-separated approved image hosts into a list."""
        return [h.strip() for h in self.allowed_image_hosts.split(",") if h.strip()]

    @property
    def csp_connect_origin_list(self) -> list[str]:
        """Parse comma-separated CSP connect origins into a list."""
        return [o.strip() for o in self.csp_connect_origins.split(",") if o.strip()]

    @property
    def trusted_proxy_ip_list(self) -> set[str]:
        """Parse comma-separated trusted proxy IPs into a set."""
        return {ip.strip() for ip in self.trusted_proxy_ips.split(",") if ip.strip()}

    @property
    def native_filter_safe_collection_list(self) -> set[str]:
        """Parse comma-separated native filter safe collection names into a set."""
        return {
            col.strip() for col in self.native_filter_safe_collections.split(",") if col.strip()
        }

    @property
    def active_gallery_collection(self) -> str:
        """
        Return the active gallery collection name.
        Uses FRUVIA_GALLERY_COLLECTION if specified; otherwise safely falls back to QDRANT_COLLECTION.
        """
        if self.fruvia_gallery_collection and self.fruvia_gallery_collection.strip():
            return self.fruvia_gallery_collection.strip()
        return self.qdrant_collection

    @property
    def max_upload_bytes(self) -> int:
        """Maximum upload size in bytes."""
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_request_body_bytes(self) -> int:
        """Maximum raw HTTP request body size in bytes."""
        return self.max_request_body_mb * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @field_validator("quality_medium_threshold")
    @classmethod
    def validate_quality_thresholds(cls, v: float, info) -> float:
        """Ensure quality_medium_threshold <= quality_high_threshold."""
        high = info.data.get("quality_high_threshold", 0.80)
        if v > high:
            raise ValueError(
                f"quality_medium_threshold ({v}) must be <= quality_high_threshold ({high})"
            )
        return v

    @field_validator("app_env")
    @classmethod
    def validate_app_env(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        clean = v.lower().strip()
        if clean not in allowed:
            raise ValueError(f"app_env must be one of {allowed}, got '{v}'")
        return clean

    @field_validator("allowed_hosts")
    @classmethod
    def validate_production_hosts(cls, v: str | list[str], info) -> str:
        env = info.data.get("app_env", "development")
        v_str = ",".join(v) if isinstance(v, list) else str(v)
        if env == "production":
            hosts = [h.strip() for h in v_str.split(",") if h.strip()]
            if not hosts or "*" in hosts or "0.0.0.0" in hosts:
                raise ValueError(
                    "In production, ALLOWED_HOSTS must be explicitly configured without wildcards ('*') or 0.0.0.0."
                )
        return v_str

    @field_validator("cors_origins")
    @classmethod
    def validate_production_cors(cls, v: str | list[str], info) -> str:
        env = info.data.get("app_env", "development")
        v_str = ",".join(v) if isinstance(v, list) else str(v)
        if env == "production":
            origins = [o.strip() for o in v_str.split(",") if o.strip()]
            if not origins or "*" in origins:
                raise ValueError(
                    "In production, CORS_ORIGINS must be explicitly configured and cannot contain wildcard '*'."
                )
        return v_str

    @field_validator("dinov2_revision")
    @classmethod
    def validate_production_model_revision(cls, v: str, info) -> str:
        env = info.data.get("app_env", "development")
        if env == "production" and (not v or v.strip().lower() == "main" or len(v.strip()) < 40):
            raise ValueError(
                "In production, DINOV2_REVISION must be pinned to an immutable full Hugging Face commit SHA (40 hex chars), not 'main'."
            )
        return v

    @field_validator("qdrant_url")
    @classmethod
    def validate_production_qdrant_url(cls, v: str | None, info) -> str | None:
        env = info.data.get("app_env", "development")
        if env == "production" and v and not v.startswith("https://"):
            raise ValueError(f"In production, QDRANT_URL must use HTTPS, got '{v}'")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        clean = v.upper().strip()
        if clean not in allowed:
            raise ValueError(f"log_level must be one of {allowed}, got '{v}'")
        return clean


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
