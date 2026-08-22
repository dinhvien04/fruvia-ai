"""
Service for discovering and caching representative gallery images per canonical species.

Retrieves public image URLs from Qdrant Gallery collection payloads using payload-only
bounded scrolling/filtering, verified against taxonomy, sanitized for safe HTTP/HTTPS schemes,
and cached in-memory with a thread-safe TTL cache.
"""

from __future__ import annotations

import threading
import time
from typing import Any
from urllib.parse import urlparse

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.repositories.qdrant_repository import QdrantRepository, get_qdrant_repository
from app.utils.taxonomy import TaxonomyManager, get_taxonomy_manager

logger = get_logger(__name__)

DEFAULT_TTL_SECONDS = 900.0  # 15 minutes TTL
MAX_BOUNDED_SCROLL_BATCHES = 8
SCROLL_BATCH_SIZE = 500


def is_safe_image_url(
    url: str | None,
    allowed_hosts: list[str] | None = None,
    is_production: bool = False,
) -> bool:
    """
    Validate that an image URL uses http/https scheme and complies with allowed host policy.

    Policy:
    - Must be a non-empty string.
    - Must use http or https scheme.
    - Must have a valid network location (hostname).
    - Reject javascript:, data:, file:, vbscript:, relative paths.
    - If allowed_hosts is configured (non-empty): hostname MUST match one of the allowed hosts.
    - If allowed_hosts is empty:
        - In production (is_production=True): FAIL CLOSED (reject all remote external hosts).
        - In development/testing (is_production=False): accept valid http/https URLs.
    """
    if not url or not isinstance(url, str):
        return False
    clean = url.strip()
    if not clean:
        return False
    try:
        parsed = urlparse(clean)
        if parsed.scheme not in ("http", "https"):
            return False
        if not parsed.netloc:
            return False
        host = (parsed.hostname or "").lower()
        if not host:
            return False

        if allowed_hosts and len(allowed_hosts) > 0:
            return any(
                host == ah.lower() or host.endswith("." + ah.lower())
                for ah in allowed_hosts
                if ah.strip()
            )

        # When allowed_hosts is empty: fail closed in production for external remote hosts
        if is_production:
            return host in {"localhost", "127.0.0.1", "testserver"}

        return True
    except Exception:
        return False


class RepresentativeImageService:
    """
    Service responsible for retrieving and caching representative images for canonical species
    from the active Qdrant Gallery collection without invoking DINOv2 embedding or vector search.
    """

    def __init__(
        self,
        qdrant_repo: QdrantRepository | None = None,
        taxonomy_manager: TaxonomyManager | None = None,
        settings: Settings | None = None,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
    ) -> None:
        self.qdrant_repo = qdrant_repo or get_qdrant_repository()
        self.taxonomy = taxonomy_manager or get_taxonomy_manager()
        self.settings = settings or get_settings()
        self.ttl_seconds = ttl_seconds
        self._lock = threading.RLock()
        # Cache structure: canonical_class -> (timestamp, representative_image_url_or_none)
        self._cache: dict[str, tuple[float, str | None]] = {}

    def get_representative_image(self, canonical_class: str) -> str | None:
        """
        Get representative image URL for a single canonical species.
        Reuses cached value if still valid; otherwise retrieves and caches.
        """
        if not canonical_class:
            return None
        canon = canonical_class.strip().lower()

        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(canon)
            if cached is not None and (now - cached[0]) < self.ttl_seconds:
                return cached[1]

        # Fetch for missing species
        images_map = self.get_representative_images([canon])
        return images_map.get(canon)

    def get_representative_images(
        self, canonical_classes: list[str] | None = None
    ) -> dict[str, str | None]:
        """
        Retrieve representative image URLs for a list of canonical species (or all taxonomy species).
        Thread-safe, TTL cached, resilient to Qdrant downtime.
        """
        self.taxonomy.load()
        if canonical_classes is None:
            target_classes = list(self.taxonomy.taxonomy.keys())
        else:
            target_classes = [c.strip().lower() for c in canonical_classes if c and c.strip()]

        now = time.monotonic()
        missing_classes: list[str] = []
        result: dict[str, str | None] = {}

        with self._lock:
            for cls_name in target_classes:
                cached = self._cache.get(cls_name)
                if cached is not None and (now - cached[0]) < self.ttl_seconds:
                    result[cls_name] = cached[1]
                else:
                    missing_classes.append(cls_name)

        if not missing_classes:
            return result

        # Retrieve missing species images from Qdrant Gallery in a single bounded scan
        fetched_images = self._fetch_from_qdrant(missing_classes)

        with self._lock:
            now_write = time.monotonic()
            for cls_name in missing_classes:
                img_url = fetched_images.get(cls_name)
                self._cache[cls_name] = (now_write, img_url)
                result[cls_name] = img_url

        return result

    def _fetch_from_qdrant(self, target_classes: list[str]) -> dict[str, str | None]:
        """
        Internal retrieval from Qdrant Gallery using a single bounded batch scroll.
        Never executes N separate queries for N species.
        Continues checking candidate points until a valid, allowed image_url is found.
        Gracefully returns None for species not found or when Qdrant is unavailable.
        """
        found_map: dict[str, str | None] = {cls_name: None for cls_name in target_classes}
        remaining_targets = set(target_classes)
        if not remaining_targets:
            return found_map

        try:
            client = self.qdrant_repo.client
            collection_name = self.qdrant_repo.collection_name
            allowed_hosts = self.settings.allowed_image_host_list or None
            is_prod = self.settings.is_production

            offset: Any = None
            payload_fields = [
                "canonical_class",
                "original_class",
                "display_name",
                "image_url",
            ]

            for batch_idx in range(MAX_BOUNDED_SCROLL_BATCHES):
                if not remaining_targets:
                    break

                try:
                    points, offset = client.scroll(
                        collection_name=collection_name,
                        limit=SCROLL_BATCH_SIZE,
                        offset=offset,
                        with_payload=payload_fields,
                        with_vectors=False,
                    )
                except Exception as e:
                    logger.warning(
                        "Representative image bounded scroll failed at batch %d: %s",
                        batch_idx + 1,
                        e,
                    )
                    break

                if not points:
                    break

                for pt in points:
                    pl = pt.payload or {}
                    raw_url = pl.get("image_url")
                    if not raw_url or not is_safe_image_url(
                        raw_url, allowed_hosts=allowed_hosts, is_production=is_prod
                    ):
                        continue

                    # Resolve canonical class
                    c_cls, _, _, _ = self.taxonomy.resolve(
                        original_class=pl.get("original_class") or "",
                        payload_canonical=pl.get("canonical_class"),
                        payload_display=pl.get("display_name"),
                    )

                    if c_cls in remaining_targets:
                        found_map[c_cls] = raw_url
                        remaining_targets.remove(c_cls)
                        if not remaining_targets:
                            break

                if not offset:
                    break

        except Exception as qdrant_err:
            logger.warning(
                "Failed to fetch representative gallery images from Qdrant: %s", qdrant_err
            )

        return found_map

    def clear_cache(self) -> None:
        """Clear all cached representative images."""
        with self._lock:
            self._cache.clear()


_representative_image_service: RepresentativeImageService | None = None


def get_representative_image_service() -> RepresentativeImageService:
    """Return singleton RepresentativeImageService instance."""
    global _representative_image_service
    if _representative_image_service is None:
        _representative_image_service = RepresentativeImageService()
    return _representative_image_service
