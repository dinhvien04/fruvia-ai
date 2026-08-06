"""
Unit tests for class_resolver utility functions.
"""

from __future__ import annotations

import pytest

from app.utils.class_resolver import format_display_name, resolve_class_names

pytestmark = pytest.mark.unit


class TestClassResolver:
    """Tests for raw class label resolution into canonical_class and display_name."""

    @pytest.mark.parametrize(
        "raw_label,expected_canonical,expected_display",
        [
            ("apple_red_2", "apple", "Apple"),
            ("apple_golden_1", "apple", "Apple"),
            ("apple_granny_smith_1", "apple", "Apple"),
            ("pear_13", "pear", "Pear"),
            ("papaya_2", "papaya", "Papaya"),
            ("orange_4", "orange", "Orange"),
            ("banana_1", "banana", "Banana"),
            ("strawberry_1", "strawberry", "Strawberry"),
            ("grape_white_3", "grape", "Grape"),
            ("dragon_fruit_1", "dragon_fruit", "Dragon Fruit"),
            ("Apple Red 2", "apple", "Apple"),
            ("Pear Williams", "pear", "Pear"),
            ("Tomato 1", "tomato", "Tomato"),
        ],
    )
    def test_class_name_resolution(
        self, raw_label: str, expected_canonical: str, expected_display: str
    ) -> None:
        canonical, display = resolve_class_names(raw_label)
        assert canonical == expected_canonical
        assert display == expected_display

    def test_class_name_resolution_with_mapping(self) -> None:
        custom_mapping = {"Apple Golden 1": "apple", "Pear 2": "pear"}
        canonical, display = resolve_class_names("Apple Golden 1", custom_mapping)
        assert canonical == "apple"
        assert display == "Apple"

    def test_format_display_name(self) -> None:
        assert format_display_name("apple") == "Apple"
        assert format_display_name("dragon_fruit") == "Dragon Fruit"
        assert format_display_name("") == "Unknown"
