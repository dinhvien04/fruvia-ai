"""
Image retrieval API route handlers.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.core.exceptions import ImageValidationError
from app.schemas.retrieval import RetrievalResponse
from app.services.retrieval_service import RetrievalService, get_retrieval_service

router = APIRouter(tags=["retrieval"])


@router.post("/retrieve", response_model=RetrievalResponse)
async def retrieve_images(
    file: Annotated[UploadFile, File(description="Query image file (JPG, PNG, WEBP)")],
    top_k: Annotated[int, Form(description="Number of similar images to retrieve (1-20)")] = 5,
    service: Annotated[RetrievalService, Depends(get_retrieval_service)] = None,  # type: ignore[assignment]
) -> RetrievalResponse:
    """
    Search for visually similar fruit images using DINOv2 vector embeddings.

    Upload an image file and retrieve top_k visually similar images stored in Qdrant Cloud.
    """
    if not (1 <= top_k <= 20):
        raise ImageValidationError(
            message="top_k must be between 1 and 20.",
            detail=f"Invalid top_k parameter: {top_k}",
        )

    file_bytes = await file.read()
    filename = file.filename or "uploaded_image.jpg"

    return service.retrieve_similar(
        file_bytes=file_bytes,
        filename=filename,
        top_k=top_k,
    )
