"""
Service for discovering and caching representative gallery images per canonical species.

Primary Source: Deterministic pre-generated manifest (`configs/representative_images.json`).
Provides O(1) in-memory lookup with runtime HTTP/HTTPS scheme and allowed-host security validation.
Maintains an optional fallback to Qdrant Gallery bounded payload scrolling when the manifest is missing.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.repositories.qdrant_repository import QdrantRepository, get_qdrant_repository
from app.utils.file_utils import load_json_file
from app.utils.taxonomy import TaxonomyManager, get_taxonomy_manager

logger = get_logger(__name__)

DEFAULT_TTL_SECONDS = 900.0  # 15 minutes TTL for fallback cache
MAX_BOUNDED_SCROLL_BATCHES = 8
SCROLL_BATCH_SIZE = 2000

_logged_empty_hosts_warning = False


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
            allowed = any(
                host == ah.lower() or host.endswith("." + ah.lower())
                for ah in allowed_hosts
                if ah.strip()
            )
            if not allowed:
                logger.debug("Image host '%s' rejected by ALLOWED_IMAGE_HOSTS allowlist.", host)
            return allowed

        # When allowed_hosts is empty: fail closed in production for external remote hosts
        if is_production:
            return host in {"localhost", "127.0.0.1", "testserver"}

        return True
    except Exception:
        return False


class RepresentativeImageService:
    """
    Service responsible for retrieving and caching representative images for canonical species.
    Uses configs/representative_images.json as primary deterministic source with runtime URL validation.
    Falls back to payload-only Qdrant Gallery inspection if the manifest is unavailable.
    """

    def __init__(
        self,
        manifest_path: Path | None = None,
        qdrant_repo: QdrantRepository | None = None,
        taxonomy_manager: TaxonomyManager | None = None,
        settings: Settings | None = None,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
    ) -> None:
        self.settings = settings or get_settings()
        self.manifest_path = manifest_path or self.settings.representative_images_manifest_path
        self.qdrant_repo = qdrant_repo or get_qdrant_repository()
        self.taxonomy = taxonomy_manager or get_taxonomy_manager()
        self.ttl_seconds = ttl_seconds
        self._lock = threading.RLock()

        # In-memory manifest storage: canonical_class -> image_url
        self._manifest_loaded = False
        self._manifest_images: dict[str, str | None] = {}
        self._manifest_collection: str | None = None

        # Fallback cache structure: canonical_class -> (timestamp, representative_image_url_or_none)
        self._fallback_cache: dict[str, tuple[float, str | None]] = {}

        self._check_startup_allowed_hosts()
        self.load_manifest()

    def _check_startup_allowed_hosts(self) -> None:
        global _logged_empty_hosts_warning
        if not _logged_empty_hosts_warning and not self.settings.allowed_image_host_list:
            _logged_empty_hosts_warning = True
            logger.warning(
                "Remote representative images are not allowed by CSP because ALLOWED_IMAGE_HOSTS is empty."
            )

    def load_manifest(self, force_reload: bool = False) -> bool:
        """
        Load deterministic representative images manifest from JSON file.
        Thread-safe, executes once unless force_reload=True.
        """
        with self._lock:
            if self._manifest_loaded and not force_reload:
                return True

            if not self.manifest_path or not self.manifest_path.exists():
                logger.info(
                    "Representative image manifest not found at %s. Will use Qdrant fallback if needed.",
                    self.manifest_path,
                )
                self._manifest_loaded = False
                self._manifest_images = {}
                return False

            try:
                data = load_json_file(self.manifest_path)
                if not isinstance(data, dict):
                    logger.warning("Invalid manifest format at %s", self.manifest_path)
                    return False

                self._manifest_collection = data.get("collection")
                raw_images = data.get("images", {})
                loaded_map: dict[str, str | None] = {}

                if isinstance(raw_images, dict):
                    for canon_cls, entry in raw_images.items():
                        canon_key = str(canon_cls).strip().lower()
                        if isinstance(entry, dict):
                            img_url = entry.get("image_url")
                        elif isinstance(entry, str):
                            img_url = entry
                        else:
                            img_url = None

                        if img_url and isinstance(img_url, str):
                            loaded_map[canon_key] = img_url.strip()
                        else:
                            loaded_map[canon_key] = None

                self._manifest_images = loaded_map
                self._manifest_loaded = True
                logger.info(
                    "Loaded representative image manifest from %s (%d species covered).",
                    self.manifest_path,
                    len(self._manifest_images),
                )
                return True
            except Exception as e:
                logger.warning("Failed to load representative image manifest: %s", e)
                self._manifest_loaded = False
                self._manifest_images = {}
                return False

    def get_representative_image(self, canonical_class: str) -> str | None:
        """
        Get representative image URL for a single canonical species.
        O(1) lookup from manifest with runtime URL safety validation.
        """
        if not canonical_class:
            return None
        canon = canonical_class.strip().lower()
        images_map = self.get_representative_images([canon])
        return images_map.get(canon)

    def get_representative_images(
        self, canonical_classes: list[str] | None = None
    ) -> dict[str, str | None]:
        """
        Retrieve representative image URLs for a list of canonical species (or all taxonomy species).
        Primary source: Manifest JSON (O(1) in-memory lookup).
        Applies runtime URL security validation (scheme & allowed hosts).
        Falls back to Qdrant Gallery bounded scan only if manifest is absent or species is missing.
        """
        self.taxonomy.load()
        if canonical_classes is None:
            target_classes = list(self.taxonomy.taxonomy.keys())
        else:
            target_classes = [c.strip().lower() for c in canonical_classes if c and c.strip()]

        allowed_hosts = self.settings.allowed_image_host_list or None
        is_prod = self.settings.is_production
        now = time.monotonic()

        result: dict[str, str | None] = {}
        missing_for_fallback: list[str] = []

        with self._lock:
            # 1. First pass: check pre-loaded manifest
            if self._manifest_loaded:
                for cls_name in target_classes:
                    if cls_name in self._manifest_images:
                        raw_url = self._manifest_images[cls_name]
                        if raw_url and is_safe_image_url(
                            raw_url, allowed_hosts=allowed_hosts, is_production=is_prod
                        ):
                            result[cls_name] = raw_url
                        else:
                            result[cls_name] = None
                    else:
                        # Check fallback cache
                        cached = self._fallback_cache.get(cls_name)
                        if cached is not None and (now - cached[0]) < self.ttl_seconds:
                            result[cls_name] = cached[1]
                        else:
                            missing_for_fallback.append(cls_name)
            else:
                # Manifest not available: check fallback TTL cache
                for cls_name in target_classes:
                    cached = self._fallback_cache.get(cls_name)
                    if cached is not None and (now - cached[0]) < self.ttl_seconds:
                        result[cls_name] = cached[1]
                    else:
                        missing_for_fallback.append(cls_name)

        if not missing_for_fallback:
            return result

        # 2. Fallback pass: retrieve missing species from Qdrant Gallery
        fetched_images, is_transient_error = self._fetch_from_qdrant(missing_for_fallback)

        with self._lock:
            now_write = time.monotonic()
            for cls_name in missing_for_fallback:
                raw_url = fetched_images.get(cls_name)
                valid_url = (
                    raw_url
                    if (
                        raw_url
                        and is_safe_image_url(
                            raw_url, allowed_hosts=allowed_hosts, is_production=is_prod
                        )
                    )
                    else None
                )

                if not is_transient_error:
                    self._fallback_cache[cls_name] = (now_write, valid_url)
                result[cls_name] = valid_url

        return result

    def _fetch_from_qdrant(self, target_classes: list[str]) -> tuple[dict[str, str | None], bool]:
        """
        Optional fallback retrieval from Qdrant Gallery when manifest is not available.
        Uses MatchAny indexed payload filter when canonical_class index is available;
        falls back to single bounded batch scrolling for legacy collections.
        Returns: (found_map, is_transient_error)
        """
        found_map: dict[str, str | None] = {cls_name: None for cls_name in target_classes}
        remaining_targets = set(target_classes)
        if not remaining_targets:
            return found_map, False

        try:
            client = self.qdrant_repo.client
            collection_name = self.qdrant_repo.collection_name
            allowed_hosts = self.settings.allowed_image_host_list or None
            is_prod = self.settings.is_production
            payload_fields = [
                "canonical_class",
                "original_class",
                "display_name",
                "image_url",
            ]

            filter_caps = self.qdrant_repo.get_filter_capabilities(collection_name)

            # Strategy A: Indexed MatchAny filter if canonical_class has keyword index
            if "canonical_class" in filter_caps:
                from qdrant_client.models import FieldCondition, Filter, MatchAny

                try:
                    scroll_filter = Filter(
                        must=[
                            FieldCondition(
                                key="canonical_class",
                                match=MatchAny(any=list(remaining_targets)),
                            )
                        ]
                    )
                    offset: Any = None
                    for _ in range(MAX_BOUNDED_SCROLL_BATCHES):
                        if not remaining_targets:
                            break
                        points, offset = client.scroll(
                            collection_name=collection_name,
                            scroll_filter=scroll_filter,
                            limit=SCROLL_BATCH_SIZE,
                            offset=offset,
                            with_payload=payload_fields,
                            with_vectors=False,
                        )
                        if not points:
                            break
                        for pt in points:
                            pl = pt.payload or {}
                            raw_url = pl.get("image_url")
                            if not raw_url or not is_safe_image_url(
                                raw_url, allowed_hosts=allowed_hosts, is_production=is_prod
                            ):
                                continue
                            c_cls, _, _, _ = self.taxonomy.resolve(
                                original_class=pl.get("original_class") or "",
                                payload_canonical=pl.get("canonical_class"),
                                payload_display=pl.get("display_name"),
                            )
                            if c_cls in remaining_targets:
                                found_map[c_cls] = raw_url
                                remaining_targets.remove(c_cls)
                        if not offset:
                            break

                    return found_map, False
                except Exception as filter_err:
                    logger.debug(
                        "MatchAny indexed scroll failed, falling back to bounded scroll: %s",
                        filter_err,
                    )

            # Strategy B: Bounded payload-only scroll for collections without keyword index
            offset = None
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
                    return found_map, True

                if not points:
                    break

                for pt in points:
                    pl = pt.payload or {}
                    raw_url = pl.get("image_url")
                    if not raw_url or not is_safe_image_url(
                        raw_url, allowed_hosts=allowed_hosts, is_production=is_prod
                    ):
                        continue

                    # Resolve canonical class via TaxonomyManager
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

            return found_map, False

        except Exception as qdrant_err:
            logger.warning(
                "Failed to fetch representative gallery images from Qdrant fallback: %s",
                qdrant_err,
            )
            return found_map, True

    def clear_cache(self) -> None:
        """Clear manifest and fallback cache."""
        with self._lock:
            self._manifest_loaded = False
            self._manifest_images.clear()
            self._fallback_cache.clear()


_representative_image_service: RepresentativeImageService | None = None


def get_representative_image_service() -> RepresentativeImageService:
    """Return singleton RepresentativeImageService instance."""
    global _representative_image_service
    if _representative_image_service is None:
        _representative_image_service = RepresentativeImageService()
    return _representative_image_service
