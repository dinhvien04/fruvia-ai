"""
File and path utilities.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import yaml


def generate_stable_uuid(namespace_str: str, *parts: str) -> str:
    """
    Generate a deterministic UUID5 from a namespace string and parts.

    Used for Qdrant point IDs so re-running upload does not create duplicates.

    Parameters
    ----------
    namespace_str : str
        A fixed namespace string (e.g. model name).
    *parts : str
        Additional parts to include (image_id, dataset_version, etc.).

    Returns
    -------
    str
        UUID5 hex string.
    """
    namespace = uuid.UUID("a3f1b2c4-d5e6-4f7a-8b9c-0d1e2f3a4b5c")
    combined = "|".join([namespace_str] + list(parts))
    return str(uuid.uuid5(namespace, combined))


def load_yaml_config(path: Path) -> dict:
    """Load a YAML configuration file."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_class_list(classes_yaml_path: Path) -> list[str]:
    """Load the ordered class list from classes.yaml."""
    cfg = load_yaml_config(classes_yaml_path)
    classes = cfg.get("classes", [])
    if not isinstance(classes, list):
        raise ValueError(f"Expected 'classes' to be a list in {classes_yaml_path}")
    return classes


def load_class_mapping(mapping_yaml_path: Path) -> dict:
    """Load original→target class mapping from class_mapping.yaml."""
    cfg = load_yaml_config(mapping_yaml_path)
    mapping = cfg.get("class_mapping", {})
    if not isinstance(mapping, dict):
        raise ValueError(f"Expected 'class_mapping' to be a dict in {mapping_yaml_path}")
    return mapping
