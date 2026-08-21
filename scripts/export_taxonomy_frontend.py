"""
Export taxonomy configurations from configs/taxonomy.yaml to frontend/data/species.json.

This script parses taxonomy.yaml and produces a structured species JSON file
used by the Fruvia frontend (Explore page, autocomplete, details).
It strictly exports only ground truth taxonomy data (English & Vietnamese names,
category, biological aliases, is_fruit flag). It NEVER fabricates nutrition or
unsupported AI claims.
"""

import json
import sys
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
TAXONOMY_PATH = ROOT_DIR / "configs" / "taxonomy.yaml"
OUTPUT_PATH = ROOT_DIR / "frontend" / "data" / "species.json"


def export_taxonomy():
    if not TAXONOMY_PATH.exists():
        print(f"Error: Taxonomy file not found at {TAXONOMY_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(TAXONOMY_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    taxonomy = data.get("taxonomy", {})
    species_list = []

    for key, info in sorted(taxonomy.items()):
        item = {
            "id": key,
            "name_en": info.get("name_en", key.replace("_", " ").title()),
            "name_vi": info.get("name_vi", key.replace("_", " ").title()),
            "category": info.get("category", "other"),
            "is_fruit": info.get("is_fruit", True),
            "aliases": info.get("aliases", []),
        }
        species_list.append(item)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(species_list, f, ensure_ascii=False, indent=2)

    print(f"Successfully exported {len(species_list)} species to {OUTPUT_PATH}")


if __name__ == "__main__":
    export_taxonomy()
