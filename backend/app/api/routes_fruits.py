"""
Taxonomy & Species discovery API routes.

Provides read-only access to canonical biological species, Vietnamese/English
names, categories, alias mappings sourced strictly from configs/taxonomy.yaml,
and representative gallery images.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.services.representative_image_service import (
    RepresentativeImageService,
    get_representative_image_service,
)
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
    representative_image_url: str | None = Field(
        default=None, description="Representative public thumbnail image URL from gallery"
    )


class SpeciesListResponse(BaseModel):
    """Response containing list of canonical species."""

    total: int = Field(..., description="Total matching species count")
    items: list[SpeciesResponse] = Field(..., description="List of canonical species")


def _to_schema(item: TaxonomyItem, representative_image_url: str | None = None) -> SpeciesResponse:
    return SpeciesResponse(
        canonical_class=item.canonical_class,
        name_en=item.name_en,
        name_vi=item.name_vi,
        category=item.category,
        is_fruit=item.is_fruit,
        aliases=item.aliases or [],
        representative_image_url=representative_image_url,
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
    image_service: Annotated[
        RepresentativeImageService, Depends(get_representative_image_service)
    ] = None,  # type: ignore[assignment]
) -> SpeciesListResponse:
    """
    List all normalized canonical species from taxonomy.yaml.
    Supports optional category filtering and search queries.
    Enriches with representative gallery images if available.
    """
    tax_mgr = get_taxonomy_manager()
    items = tax_mgr.list_items(category=category, search_query=q)

    canonical_classes = [it.canonical_class for it in items]
    rep_images = image_service.get_representative_images(canonical_classes) if image_service else {}

    return SpeciesListResponse(
        total=len(items),
        items=[
            _to_schema(it, representative_image_url=rep_images.get(it.canonical_class))
            for it in items
        ],
    )


@router.get("/species/{canonical_class}", response_model=SpeciesResponse)
async def get_species(
    canonical_class: str,
    image_service: Annotated[
        RepresentativeImageService, Depends(get_representative_image_service)
    ] = None,  # type: ignore[assignment]
) -> SpeciesResponse:
    """
    Get detailed canonical species information by identifier.
    """
    tax_mgr = get_taxonomy_manager()
    clean_class = canonical_class.lower().strip()
    item = tax_mgr.get_item(clean_class)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Species '{canonical_class}' not found in taxonomy.",
        )
    rep_img = image_service.get_representative_image(clean_class) if image_service else None
    return _to_schema(item, representative_image_url=rep_img)
