"""
Fruvia AI exception hierarchy and FastAPI error handlers.

All user-facing errors extend FruviaError so a single handler
can catch them and return a consistent JSON body.  Internal
details are logged but never leaked to the client.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger(__name__)


# ================================================================
# Base exception
# ================================================================


class FruviaError(Exception):
    """Base exception for all Fruvia AI domain errors."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    message: str = "An internal error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        detail: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message or self.__class__.message
        self.detail = detail  # internal detail, logged but not sent to client
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": True,
            "error_code": self.error_code,
            "message": self.message,
        }


# ================================================================
# Concrete errors
# ================================================================


class ImageValidationError(FruviaError):
    """Raised when an uploaded image fails validation."""

    status_code = 400
    error_code = "INVALID_IMAGE"
    message = "The uploaded file is not a valid image."


class FileTooLargeError(FruviaError):
    """Raised when the upload exceeds the size limit."""

    status_code = 413
    error_code = "FILE_TOO_LARGE"
    message = "The uploaded file exceeds the maximum allowed size."


class UnsupportedFormatError(FruviaError):
    """Raised when the image format is not supported."""

    status_code = 415
    error_code = "UNSUPPORTED_FORMAT"
    message = "Only JPG, JPEG, PNG and WEBP images are accepted."


class ModelNotLoadedError(FruviaError):
    """Raised when the ML model is not available."""

    status_code = 503
    error_code = "MODEL_NOT_LOADED"
    message = "The classification model is not loaded. Please try again later."


class ImageEncodingError(FruviaError):
    """Raised when feature extraction with DINOv2 fails."""

    status_code = 500
    error_code = "ENCODING_FAILED"
    message = "Failed to extract features from the image."


class QdrantConnectionError(FruviaError):
    """Raised when Qdrant Cloud is unreachable."""

    status_code = 503
    error_code = "QDRANT_UNAVAILABLE"
    message = "The image search service is temporarily unavailable."


class QdrantCollectionNotFoundError(FruviaError):
    """Raised when the specified Qdrant collection does not exist."""

    status_code = 503
    error_code = "COLLECTION_NOT_FOUND"
    message = "The search collection is not available. Please try again later."


class QdrantSchemaIncompatibleError(FruviaError):
    """Raised when a Qdrant collection's schema (dimension, distance, status) is incompatible."""

    status_code = 503
    error_code = "COLLECTION_SCHEMA_INCOMPATIBLE"
    message = "The search collection schema is incompatible with the current system."


class LowConfidenceError(FruviaError):
    """Not really an error — used to signal low-confidence results."""

    status_code = 200  # still 200, but accepted=False in body
    error_code = "LOW_CONFIDENCE"
    message = "The model confidence is below the acceptance threshold."


# ================================================================
# FastAPI exception handlers
# ================================================================


async def fruvia_error_handler(request: Request, exc: FruviaError) -> JSONResponse:
    """Handle all FruviaError subclasses uniformly."""
    if exc.detail:
        logger.warning("FruviaError [%s]: %s | detail=%s", exc.error_code, exc.message, exc.detail)
    else:
        logger.warning("FruviaError [%s]: %s", exc.error_code, exc.message)
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions — log but never expose internals."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "error_code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred. Please try again later.",
        },
    )
