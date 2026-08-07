"""
Image retrieval API route handlers.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.exceptions import ImageValidationError
from app.schemas.retrieval import RetrievalResponse
from app.services.retrieval_service import RetrievalService, get_retrieval_service
from app.utils.image_validation import read_upload_bounded

router = APIRouter(tags=["retrieval"])


@router.post("/retrieve", response_model=RetrievalResponse)
async def retrieve_images(
    file: Annotated[UploadFile, File(description="Query image file (JPG, PNG, WEBP)")],
    top_k: Annotated[int, Form(description="Number of similar images to retrieve (1-20)")] = 5,
    mode: Annotated[str, Form(description="Retrieval mode: 'image' or 'class'")] = "image",
    category: Annotated[
        str,
        Form(description="Category filter: 'all', 'fruit', 'vegetable', 'nut', 'seed', 'other'"),
    ] = "all",
    service: Annotated[RetrievalService, Depends(get_retrieval_service)] = None,  # type: ignore[assignment]
) -> RetrievalResponse:
    """
    Search for visually similar fruit images using DINOv2 vector embeddings.

    Upload an image file and retrieve top_k visually similar images stored in Qdrant Cloud.
    Features:
    - Bounded streaming file read to protect RAM
    - Support search modes: image (top individual images) vs class (deduplicated species)
    - Optional category filtering (fruit, vegetable, nut, seed, all)
    - Offloads CPU-intensive DINOv2 feature extraction and Qdrant queries to threadpool
    """
    if not (1 <= top_k <= 20):
        raise ImageValidationError(
            message="top_k must be between 1 and 20.",
            detail=f"Invalid top_k parameter: {top_k}",
        )

    mode_clean = mode.lower().strip()
    if mode_clean not in {"image", "class"}:
        raise ImageValidationError(
            message="mode must be either 'image' or 'class'.",
            detail=f"Invalid mode parameter: {mode}",
        )

    cat_clean = category.lower().strip()
    allowed_categories = {"all", "fruit", "vegetable", "nut", "seed", "other"}
    if cat_clean not in allowed_categories:
        raise ImageValidationError(
            message=f"category must be one of {allowed_categories}.",
            detail=f"Invalid category parameter: {category}",
        )

    settings = get_settings()

    # Bounded streaming read up to max_upload_bytes + 1
    file_bytes = await read_upload_bounded(file, max_bytes=settings.max_upload_bytes)
    filename = file.filename or "uploaded_image.jpg"
    content_type = file.content_type

    # Offload CPU-bound ML & synchronous Qdrant query to threadpool to avoid blocking event loop
    return await run_in_threadpool(
        service.retrieve_similar,
        file_bytes=file_bytes,
        filename=filename,
        top_k=top_k,
        mode=mode_clean,
        category=cat_clean,
        content_type=content_type,
    )
