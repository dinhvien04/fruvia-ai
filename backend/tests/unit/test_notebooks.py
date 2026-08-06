"""
Unit tests for notebook structure validation.

These tests verify that Colab notebooks are valid JSON with correct metadata,
contain no outputs, no secrets, and no local machine paths. They do NOT
execute the notebooks — notebooks are designed to run on Google Colab only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

# ── Notebook paths (relative to project root) ──────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[3]  # backend/tests/unit/ → project root
NOTEBOOKS_DIR = PROJECT_ROOT / "notebooks"

NOTEBOOK_FILES = sorted(NOTEBOOKS_DIR.glob("*.ipynb"))

# Notebooks that require GPU runtime
GPU_NOTEBOOKS = {"06_generate_dinov2_embeddings.ipynb"}

# Patterns that indicate hardcoded secrets
SECRET_PATTERNS = [
    r'api_key\s*=\s*["\'][^"\']{10,}',  # api_key = "actual-key"
    r'QDRANT_API_KEY\s*=\s*["\'][^"\']{10,}',  # QDRANT_API_KEY = "..."
    r'QDRANT_URL\s*=\s*["\']https://[^"\']+qdrant',  # hardcoded Qdrant URL
    r'KAGGLE_KEY\s*=\s*["\'][^"\']{10,}',  # KAGGLE_KEY = "..."
    r"\bsk-[a-zA-Z0-9]{20,}",  # OpenAI-style key
    r'api_key\s*:\s*["\'][^"\']{10,}',  # YAML-style api_key: "..."
]

# Patterns that indicate local Windows paths
WINDOWS_PATH_PATTERNS = [
    r"[A-Z]:\\",  # C:\ D:\ etc.
    r"\\Users\\",  # \Users\username
    r"\\AppData\\",  # \AppData\
]


def _get_notebook_ids() -> list[str]:
    """Return notebook filenames for parametrize IDs."""
    return [nb.name for nb in NOTEBOOK_FILES]


def _load_notebook(path: Path) -> dict:
    """Load and parse a notebook JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _get_all_source_lines(nb: dict) -> list[str]:
    """Extract all source lines from all cells in a notebook."""
    lines = []
    for cell in nb.get("cells", []):
        source = cell.get("source", [])
        if isinstance(source, list):
            lines.extend(source)
        elif isinstance(source, str):
            lines.append(source)
    return lines


# ── Skip if no notebooks exist yet ──────────────────────────────────────────

if not NOTEBOOK_FILES:
    pytest.skip("No notebooks found in notebooks/ directory", allow_module_level=True)


# ── Tests ───────────────────────────────────────────────────────────────────


class TestNotebookJsonStructure:
    """Verify notebook files are valid Jupyter JSON."""

    @pytest.mark.parametrize("nb_path", NOTEBOOK_FILES, ids=_get_notebook_ids())
    def test_valid_json(self, nb_path: Path) -> None:
        """Notebook must be valid JSON."""
        nb = _load_notebook(nb_path)
        assert isinstance(nb, dict)

    @pytest.mark.parametrize("nb_path", NOTEBOOK_FILES, ids=_get_notebook_ids())
    def test_has_nbformat(self, nb_path: Path) -> None:
        """Notebook must declare nbformat version."""
        nb = _load_notebook(nb_path)
        assert "nbformat" in nb
        assert nb["nbformat"] >= 4

    @pytest.mark.parametrize("nb_path", NOTEBOOK_FILES, ids=_get_notebook_ids())
    def test_has_cells(self, nb_path: Path) -> None:
        """Notebook must have at least one cell."""
        nb = _load_notebook(nb_path)
        assert "cells" in nb
        assert len(nb["cells"]) > 0

    @pytest.mark.parametrize("nb_path", NOTEBOOK_FILES, ids=_get_notebook_ids())
    def test_has_kernelspec(self, nb_path: Path) -> None:
        """Notebook must have a kernelspec in metadata."""
        nb = _load_notebook(nb_path)
        metadata = nb.get("metadata", {})
        assert "kernelspec" in metadata
        assert metadata["kernelspec"].get("name") == "python3"


class TestNotebookNoOutputs:
    """Notebooks must be committed with zero outputs and no execution counts."""

    @pytest.mark.parametrize("nb_path", NOTEBOOK_FILES, ids=_get_notebook_ids())
    def test_no_cell_outputs(self, nb_path: Path) -> None:
        """No code cell should have non-empty outputs."""
        nb = _load_notebook(nb_path)
        for i, cell in enumerate(nb["cells"]):
            if cell.get("cell_type") == "code":
                outputs = cell.get("outputs", [])
                assert outputs == [], f"Cell {i} in {nb_path.name} has non-empty outputs"

    @pytest.mark.parametrize("nb_path", NOTEBOOK_FILES, ids=_get_notebook_ids())
    def test_no_execution_count(self, nb_path: Path) -> None:
        """No code cell should have a non-null execution_count."""
        nb = _load_notebook(nb_path)
        for i, cell in enumerate(nb["cells"]):
            if cell.get("cell_type") == "code":
                exec_count = cell.get("execution_count")
                assert exec_count is None, (
                    f"Cell {i} in {nb_path.name} has execution_count={exec_count}"
                )


class TestNotebookNoSecrets:
    """Notebooks must not contain hardcoded API keys or secrets."""

    @pytest.mark.parametrize("nb_path", NOTEBOOK_FILES, ids=_get_notebook_ids())
    def test_no_hardcoded_secrets(self, nb_path: Path) -> None:
        """Source cells must not contain patterns that look like hardcoded secrets."""
        nb = _load_notebook(nb_path)
        all_source = "\n".join(_get_all_source_lines(nb))

        for pattern in SECRET_PATTERNS:
            matches = re.findall(pattern, all_source, re.IGNORECASE)
            assert not matches, (
                f"{nb_path.name} contains potential secret matching "
                f"pattern '{pattern}': {matches[:3]}"
            )


class TestNotebookNoPaths:
    """Notebooks must not contain Windows-style local paths."""

    @pytest.mark.parametrize("nb_path", NOTEBOOK_FILES, ids=_get_notebook_ids())
    def test_no_windows_paths(self, nb_path: Path) -> None:
        """Source cells must not reference Windows-style paths."""
        nb = _load_notebook(nb_path)
        all_source = "\n".join(_get_all_source_lines(nb))

        for pattern in WINDOWS_PATH_PATTERNS:
            matches = re.findall(pattern, all_source)
            assert not matches, (
                f"{nb_path.name} contains Windows path pattern '{pattern}': {matches[:3]}"
            )


class TestNotebookColabMetadata:
    """Notebooks must have Google Colab metadata."""

    @pytest.mark.parametrize("nb_path", NOTEBOOK_FILES, ids=_get_notebook_ids())
    def test_has_colab_metadata(self, nb_path: Path) -> None:
        """Notebook metadata must include colab section."""
        nb = _load_notebook(nb_path)
        metadata = nb.get("metadata", {})
        assert "colab" in metadata, f"{nb_path.name} missing colab metadata"

    def test_gpu_notebooks_have_accelerator(self) -> None:
        """GPU-required notebooks must declare GPU accelerator."""
        for nb_path in NOTEBOOK_FILES:
            if nb_path.name in GPU_NOTEBOOKS:
                nb = _load_notebook(nb_path)
                metadata = nb.get("metadata", {})
                accelerator = metadata.get("accelerator")
                gpu_type = metadata.get("colab", {}).get("gpuType")
                assert accelerator == "GPU" or gpu_type is not None, (
                    f"{nb_path.name} requires GPU but has no accelerator/gpuType metadata"
                )
