"""
Utility for resolving canonical class names and human-friendly display names from raw class labels.
"""

from __future__ import annotations

import re

# Known common fruit prefixes for heuristic fallback
COMMON_FRUIT_GROUPS = [
    "apple",
    "apricot",
    "avocado",
    "banana",
    "beetroot",
    "blueberry",
    "cactus fruit",
    "cantaloupe",
    "carambula",
    "cauliflower",
    "cherry",
    "chestnut",
    "clementine",
    "cocos",
    "corn",
    "cucumber",
    "dates",
    "dragon fruit",
    "eggplant",
    "fig",
    "ginger",
    "granadilla",
    "grape",
    "grapefruit",
    "guava",
    "hazelnut",
    "huckleberry",
    "kaki",
    "kiwi",
    "kohlrabi",
    "lemon",
    "limes",
    "lychee",
    "mandarine",
    "mango",
    "mangosteen",
    "melon",
    "nectarine",
    "nut",
    "onion",
    "orange",
    "papaya",
    "passion fruit",
    "peach",
    "pear",
    "pepino",
    "pepper",
    "physalis",
    "pineapple",
    "pitahaya",
    "plum",
    "pomegranate",
    "pomelo",
    "potato",
    "rambutan",
    "raspberry",
    "redcurrant",
    "salak",
    "strawberry",
    "tamarillo",
    "tangelo",
    "tomato",
    "walnut",
    "watermelon",
]


def resolve_class_names(
    original_class: str, class_mapping: dict[str, str] | None = None
) -> tuple[str, str]:
    """
    Resolve raw original_class label into a tuple of (canonical_class, display_name).

    Resolution logic:
    1. Exact match in class_mapping.
    2. Case-insensitive match in class_mapping.
    3. Convert underscores/hyphens to spaces and check class_mapping again.
    4. Strip numbers/varieties to match common fruit groups.
    5. Fallback: normalized slug for canonical_class, Title Case for display_name.

    Examples:
    - "apple_red_2" -> ("apple", "Apple")
    - "Apple Golden 1" -> ("apple", "Apple")
    - "pear_13" -> ("pear", "Pear")
    - "papaya_2" -> ("papaya", "Papaya")
    - "dragon_fruit" -> ("dragon_fruit", "Dragon Fruit")

    Parameters
    ----------
    original_class : str
        Raw label string from Qdrant or dataset.
    class_mapping : dict[str, str] | None
        Loaded dictionary mapping original labels to target classes.

    Returns
    -------
    tuple[str, str]
        (canonical_class, display_name)
    """
    mapping = class_mapping or {}
    raw_str = (original_class or "unknown").strip()

    # 1. Exact match in mapping
    if raw_str in mapping:
        canonical = mapping[raw_str]
        return canonical, format_display_name(canonical)

    # Lowercase mapping lookup helper
    mapping_lower = {k.lower().strip(): v for k, v in mapping.items()}

    # 2. Case-insensitive match in mapping
    raw_lower = raw_str.lower()
    if raw_lower in mapping_lower:
        canonical = mapping_lower[raw_lower]
        return canonical, format_display_name(canonical)

    # 3. Normalize underscores/hyphens to spaces & check mapping
    normalized_spaces = re.sub(r"[_\-]+", " ", raw_lower).strip()
    normalized_spaces = re.sub(r"\s+", " ", normalized_spaces)

    if normalized_spaces in mapping_lower:
        canonical = mapping_lower[normalized_spaces]
        return canonical, format_display_name(canonical)

    # 4. Strip numbers at the end (e.g. "pear 13" -> "pear", "apple red 2" -> "apple red")
    without_numbers = re.sub(r"\s+\d+$", "", normalized_spaces).strip()
    if without_numbers in mapping_lower:
        canonical = mapping_lower[without_numbers]
        return canonical, format_display_name(canonical)

    # 5. Check if any common fruit group starts the normalized string
    for fruit in COMMON_FRUIT_GROUPS:
        if without_numbers.startswith(fruit):
            canonical = fruit.replace(" ", "_")
            return canonical, format_display_name(canonical)

    # 6. Fallback: convert to machine canonical slug (snake_case without numbers)
    clean_base = re.sub(r"\s+\d+$", "", normalized_spaces)
    canonical = clean_base.replace(" ", "_")
    return canonical, format_display_name(canonical)


def format_display_name(canonical_class: str) -> str:
    """
    Convert a canonical class slug (e.g. 'apple', 'dragon_fruit') to Title Case display name.
    """
    if not canonical_class:
        return "Unknown"
    words = canonical_class.replace("_", " ").split()
    return " ".join(word.capitalize() for word in words)
