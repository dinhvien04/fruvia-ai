"""
Taxonomy & Species discovery API routes.

Provides read-only access to canonical biological species, Vietnamese/English
names, categories, and alias mappings sourced strictly from configs/taxonomy.yaml.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.utils.taxonomy import TaxonomyItem, get_taxonomy_manager

router = APIRouter(tags=["species"])


class SpeciesResponse(BaseModel):
    """Normalized canonical species item representation."""

    canonical_class: str = Field(..., description="Canonical species identifier")
    name_en: str = Field(..., description="English common name")
    name_vi: str | None = Field(default=None, description="Vietnamese common name")
    category: str = Field(..., description="Category: fruit | vegetable | nut | seed | other")
    is_fruit: bool = Field(..., description="Whether classified biologically/culinarily as fruit")
    aliases: list[str] = Field(default_factory=list, description="Dataset variant label aliases")


class SpeciesListResponse(BaseModel):
    """Response containing list of canonical species."""

    total: int = Field(..., description="Total matching species count")
    items: list[SpeciesResponse] = Field(..., description="List of canonical species")


def _to_schema(item: TaxonomyItem) -> SpeciesResponse:
    return SpeciesResponse(
        canonical_class=item.canonical_class,
        name_en=item.name_en,
        name_vi=item.name_vi,
        category=item.category,
        is_fruit=item.is_fruit,
        aliases=item.aliases or [],
    )


@router.get("/species", response_model=SpeciesListResponse)
async def list_species(
    category: Annotated[
        str | None,
        Query(description="Filter by category: fruit, vegetable, nut, seed, other, all"),
    ] = "all",
    q: Annotated[
        str | None,
        Query(description="Search keyword for English/Vietnamese name or alias"),
    ] = None,
) -> SpeciesListResponse:
    """
    List all normalized canonical species from taxonomy.yaml.
    Supports optional category filtering and search queries.
    """
    tax_mgr = get_taxonomy_manager()
    items = tax_mgr.list_items(category=category, search_query=q)
    return SpeciesListResponse(
        total=len(items),
        items=[_to_schema(it) for it in items],
    )


@router.get("/species/{canonical_class}", response_model=SpeciesResponse)
async def get_species(canonical_class: str) -> SpeciesResponse:
    """
    Get detailed canonical species information by identifier.
    """
    tax_mgr = get_taxonomy_manager()
    item = tax_mgr.get_item(canonical_class.lower().strip())
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Species '{canonical_class}' not found in taxonomy.",
        )
    return _to_schema(item)
