"""
Taxonomy management module for Fruvia AI.

Provides structured taxonomy loading, canonicalization, Vietnamese/English translation,
and category filtering across multiple datasets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger
from app.utils.file_utils import load_yaml_config

logger = get_logger(__name__)


@dataclass
class TaxonomyItem:
    """Represents a canonical entity in the taxonomy."""

    canonical_class: str
    name_en: str
    name_vi: str | None = None
    category: str = "other"  # fruit | vegetable | nut | seed | other
    is_fruit: bool = True
    aliases: list[str] | None = None


class TaxonomyManager:
    """
    Manages loading and resolving taxonomy definitions from YAML configuration.
    """

    def __init__(
        self,
        taxonomy_path: Path | None = None,
        class_mapping_path: Path | None = None,
    ) -> None:
        settings = get_settings()
        self.taxonomy_path = taxonomy_path or settings.taxonomy_path
        self.class_mapping_path = class_mapping_path or settings.class_mapping_path
        self._taxonomy_items: dict[str, TaxonomyItem] = {}
        self._alias_to_canonical: dict[str, str] = {}
        self._class_mapping: dict[str, str] = {}
        self._loaded = False

    def load(self) -> None:
        """Load taxonomy items and class mappings from YAML config files."""
        if self._loaded:
            return

        # 1. Load taxonomy.yaml
        if self.taxonomy_path.exists():
            try:
                data = load_yaml_config(self.taxonomy_path)
                tax_dict = data.get("taxonomy", {}) if isinstance(data, dict) else {}
                for key, val in tax_dict.items():
                    if not isinstance(val, dict):
                        continue
                    raw_aliases = val.get("aliases", [])
                    aliases_list = [str(a).strip() for a in raw_aliases if str(a).strip()] if isinstance(raw_aliases, list) else []

                    item = TaxonomyItem(
                        canonical_class=key,
                        name_en=val.get("name_en", key.replace("_", " ").title()),
                        name_vi=val.get("name_vi"),
                        category=val.get(
                            "category", "fruit" if val.get("is_fruit", True) else "other"
                        ),
                        is_fruit=val.get("is_fruit", True),
                        aliases=aliases_list,
                    )
                    self._taxonomy_items[key] = item
                    self._alias_to_canonical[key.lower()] = key

                    for alias in aliases_list:
                        self._alias_to_canonical[alias.lower()] = key
            except Exception as e:
                logger.warning("Failed to load taxonomy from %s: %s", self.taxonomy_path, e)

        # 2. Load class_mapping.yaml for backward compatibility
        if self.class_mapping_path.exists():
            try:
                data = load_yaml_config(self.class_mapping_path)
                mapping = data.get("class_mapping", {}) if isinstance(data, dict) else {}
                if isinstance(mapping, dict):
                    self._class_mapping = {
                        str(k).strip(): str(v).strip() for k, v in mapping.items()
                    }
            except Exception as e:
                logger.warning(
                    "Failed to load class_mapping from %s: %s", self.class_mapping_path, e
                )

        self._loaded = True

    def get_item(self, canonical_class: str) -> TaxonomyItem | None:
        """Retrieve TaxonomyItem by canonical_class slug."""
        self.load()
        return self._taxonomy_items.get(canonical_class)

    def list_items(
        self,
        category: str | None = None,
        search_query: str | None = None,
    ) -> list[TaxonomyItem]:
        """
        List taxonomy items with optional category filtering and keyword search.
        Only returns verified data from configs/taxonomy.yaml.
        """
        self.load()
        results: list[TaxonomyItem] = []

        cat_clean = category.lower().strip() if category else "all"
        query_clean = search_query.lower().strip() if search_query else ""

        for item in self._taxonomy_items.values():
            if cat_clean not in {"all", ""} and item.category != cat_clean:
                continue

            if query_clean:
                id_match = query_clean in item.canonical_class.lower()
                en_match = query_clean in item.name_en.lower()
                vi_match = item.name_vi and query_clean in item.name_vi.lower()
                alias_match = item.aliases and any(query_clean in a.lower() for a in item.aliases)
                if not (id_match or en_match or vi_match or alias_match):
                    continue

            results.append(item)

        return results

    def resolve(
        self,
        original_class: str,
        payload_canonical: str | None = None,
        payload_display: str | None = None,
    ) -> tuple[str, str, str | None, str]:
        """
        Resolve raw class label or payload fields into:
        (canonical_class, display_name_en, display_name_vi, category)

        Resolution Priority:
        1. If payload already has canonical_class, respect it!
        2. Explicit taxonomy alias match.
        3. Explicit class_mapping.yaml match.
        4. Safe heuristic normalization.
        """
        self.load()

        raw_str = (original_class or "unknown").strip()
        raw_lower = raw_str.lower()

        # Case 1: Payload already has canonical_class — verify against taxonomy/aliases
        if payload_canonical and payload_canonical.strip() and payload_canonical != "unknown":
            raw_p_canon = payload_canonical.strip()
            p_canon_lower = raw_p_canon.lower()
            p_canon_slug = re.sub(r"[_\-\s]+", "_", p_canon_lower)

            resolved_canon = None
            if p_canon_lower in self._alias_to_canonical:
                resolved_canon = self._alias_to_canonical[p_canon_lower]
            elif p_canon_slug in self._alias_to_canonical:
                resolved_canon = self._alias_to_canonical[p_canon_slug]

            if resolved_canon:
                tax_item = self._taxonomy_items[resolved_canon]
                display_en = payload_display or tax_item.name_en
                display_vi = tax_item.name_vi
                return resolved_canon, display_en, display_vi, tax_item.category
            else:
                # Taxonomy does not know this canonical_class, keep payload's value
                tax_item = self._taxonomy_items.get(raw_p_canon)
                display_en = payload_display or (
                    tax_item.name_en if tax_item else format_display_name(raw_p_canon)
                )
                display_vi = tax_item.name_vi if tax_item else None
                category = tax_item.category if tax_item else "other"
                return raw_p_canon, display_en, display_vi, category

        # Case 2: Exact or alias match in taxonomy
        if raw_lower in self._alias_to_canonical:
            canonical = self._alias_to_canonical[raw_lower]
            tax_item = self._taxonomy_items[canonical]
            return canonical, tax_item.name_en, tax_item.name_vi, tax_item.category

        # Normalized string (spaces instead of underscores/dashes)
        norm_spaces = re.sub(r"[_\-]+", " ", raw_lower).strip()
        norm_spaces = re.sub(r"\s+", " ", norm_spaces)

        norm_slug = norm_spaces.replace(" ", "_")
        if norm_slug in self._alias_to_canonical:
            canonical = self._alias_to_canonical[norm_slug]
            tax_item = self._taxonomy_items[canonical]
            return canonical, tax_item.name_en, tax_item.name_vi, tax_item.category

        # Case 3: Match in class_mapping.yaml
        if raw_str in self._class_mapping:
            canonical = self._class_mapping[raw_str]
            tax_item = self._taxonomy_items.get(canonical)
            display_en = tax_item.name_en if tax_item else format_display_name(canonical)
            display_vi = tax_item.name_vi if tax_item else None
            category = tax_item.category if tax_item else "fruit"
            return canonical, display_en, display_vi, category

        # Case-insensitive mapping check
        mapping_lower = {k.lower(): v for k, v in self._class_mapping.items()}
        if raw_lower in mapping_lower:
            canonical = mapping_lower[raw_lower]
            tax_item = self._taxonomy_items.get(canonical)
            display_en = tax_item.name_en if tax_item else format_display_name(canonical)
            display_vi = tax_item.name_vi if tax_item else None
            category = tax_item.category if tax_item else "fruit"
            return canonical, display_en, display_vi, category

        # Case 4: Strip numbers at the end (e.g. "pear 13" -> "pear", "apple_red_2" -> "apple_red")
        without_numbers = re.sub(r"\s+\d+$", "", norm_spaces).strip()
        without_numbers_slug = without_numbers.replace(" ", "_")

        if without_numbers_slug in self._alias_to_canonical:
            canonical = self._alias_to_canonical[without_numbers_slug]
            tax_item = self._taxonomy_items[canonical]
            return canonical, tax_item.name_en, tax_item.name_vi, tax_item.category

        # Check prefix matching against taxonomy canonical keys
        for key, item in self._taxonomy_items.items():
            key_spaces = key.replace("_", " ")
            if without_numbers.startswith(key_spaces):
                return key, item.name_en, item.name_vi, item.category

        # Case 5: Fallback slug
        clean_slug = without_numbers_slug or "unknown"
        display_en = format_display_name(clean_slug)
        return clean_slug, display_en, None, "other"


def format_display_name(canonical_class: str) -> str:
    """Format canonical slug into Title Case display name."""
    if not canonical_class:
        return "Unknown"
    words = canonical_class.replace("_", " ").split()
    return " ".join(word.capitalize() for word in words)


@lru_cache(maxsize=1)
def get_taxonomy_manager() -> TaxonomyManager:
    """Return cached singleton instance of TaxonomyManager."""
    manager = TaxonomyManager()
    manager.load()
    return manager
