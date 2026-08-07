"""
Unit tests for TaxonomyManager and class resolution.
"""

from __future__ import annotations

import pytest

from app.utils.taxonomy import TaxonomyManager, get_taxonomy_manager


@pytest.fixture
def taxonomy_mgr() -> TaxonomyManager:
    mgr = get_taxonomy_manager()
    mgr.load()
    return mgr


class TestTaxonomyResolution:
    def test_canonical_durian(self, taxonomy_mgr: TaxonomyManager) -> None:
        canonical, display_en, display_vi, category = taxonomy_mgr.resolve("durian")
        assert canonical == "durian"
        assert display_en == "Durian"
        assert display_vi == "Sầu riêng"
        assert category == "fruit"

    def test_canonical_dragonfruit_alias(self, taxonomy_mgr: TaxonomyManager) -> None:
        canonical, display_en, display_vi, category = taxonomy_mgr.resolve("pitahaya")
        assert canonical == "dragon_fruit"
        assert display_en == "Dragon Fruit"
        assert display_vi == "Thanh long"
        assert category == "fruit"

    def test_apple_variants(self, taxonomy_mgr: TaxonomyManager) -> None:
        for variant in ["apple_red_2", "Apple Golden 1", "apple_braeburn_3"]:
            canonical, display_en, display_vi, _ = taxonomy_mgr.resolve(variant)
            assert canonical == "apple"
            assert display_en == "Apple"
            assert display_vi == "Táo"

    def test_vegetable_category(self, taxonomy_mgr: TaxonomyManager) -> None:
        canonical, display_en, display_vi, category = taxonomy_mgr.resolve("cucumber_1")
        assert canonical == "cucumber"
        assert display_en == "Cucumber"
        assert display_vi == "Dưa leo"
        assert category == "vegetable"

    def test_nut_category(self, taxonomy_mgr: TaxonomyManager) -> None:
        canonical, display_en, display_vi, category = taxonomy_mgr.resolve("hazelnut")
        assert canonical == "hazelnut"
        assert category == "nut"

    def test_payload_override_respected(self, taxonomy_mgr: TaxonomyManager) -> None:
        canonical, display_en, display_vi, category = taxonomy_mgr.resolve(
            original_class="durian_raw_123",
            payload_canonical="durian",
            payload_display="Sầu Riêng Ngon",
        )
        assert canonical == "durian"
        assert display_en == "Sầu Riêng Ngon"
        assert display_vi == "Sầu riêng"
        assert category == "fruit"
