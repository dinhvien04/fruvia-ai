"""
Utility for resolving canonical class names and human-friendly display names from raw class labels.
Wraps TaxonomyManager for taxonomy-aware resolution.
"""

from __future__ import annotations

from app.utils.taxonomy import format_display_name, get_taxonomy_manager


def resolve_class_names(
    original_class: str, class_mapping: dict[str, str] | None = None
) -> tuple[str, str]:
    """
    Resolve raw original_class label into a tuple of (canonical_class, display_name).

    Delegates to TaxonomyManager for robust 410-class normalization and translation.
    """
    tax_mgr = get_taxonomy_manager()
    canonical, display_en, _, _ = tax_mgr.resolve(original_class=original_class)
    return canonical, display_en


__all__ = ["resolve_class_names", "format_display_name"]
