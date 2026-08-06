"""
Pydantic schemas for fruit metadata endpoints.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class FruitClassInfo(BaseModel):
    """Metadata about a single fruit class."""

    class_name: str = Field(..., description="Normalized class name")
    original_classes: List[str] = Field(
        default_factory=list,
        description="Original Fruits-360 class names mapped to this class",
    )
    sample_count: Optional[int] = Field(None, description="Number of images in gallery")


class FruitListResponse(BaseModel):
    """Response body for GET /api/fruits."""

    classes: List[str] = Field(..., description="All available fruit class names")
    total: int = Field(..., description="Total number of classes")


class FruitDetailResponse(BaseModel):
    """Response body for GET /api/fruits/{class_name}."""

    class_name: str
    original_classes: List[str] = Field(default_factory=list)
    sample_count: Optional[int] = None
    in_classifier: bool = Field(
        ..., description="Whether this class is in the classification model"
    )
