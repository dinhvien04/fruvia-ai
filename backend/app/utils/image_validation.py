"""
Image validation utilities.

Validates uploaded images by:
- Checking file size against maximum
- Verifying MIME type matches allowed formats
- Opening with Pillow to verify image integrity
- Ensuring the image is RGB-convertible
"""

from __future__ import annotations

import io
from typing import Set, Tuple

from PIL import Image

from app.core.exceptions import (
    FileTooLargeError,
    ImageValidationError,
    UnsupportedFormatError,
)

# Allowed file extensions (lowercase)
ALLOWED_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png", ".webp"}

# Pillow format names that correspond to allowed types
ALLOWED_PILLOW_FORMATS: Set[str] = {"JPEG", "PNG", "WEBP"}

# MIME types considered valid
ALLOWED_MIME_TYPES: Set[str] = {
    "image/jpeg",
    "image/png",
    "image/webp",
}


def validate_file_extension(filename: str) -> str:
    """
    Check the file extension is in the allowed set.

    Parameters
    ----------
    filename : str
        The original filename (from the upload).

    Returns
    -------
    str
        The lowercase extension including the dot.

    Raises
    ------
    UnsupportedFormatError
        If the extension is not allowed.
    """
    ext = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedFormatError(
            f"File extension '{ext}' is not supported. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    return ext


def validate_file_size(data: bytes, max_bytes: int) -> None:
    """
    Ensure the file does not exceed the size limit.

    Raises
    ------
    FileTooLargeError
        If len(data) > max_bytes.
    """
    if len(data) > max_bytes:
        max_mb = max_bytes / (1024 * 1024)
        actual_mb = len(data) / (1024 * 1024)
        raise FileTooLargeError(
            f"File size {actual_mb:.1f} MB exceeds the {max_mb:.0f} MB limit."
        )


def validate_image_content(data: bytes) -> Image.Image:
    """
    Open and verify image data with Pillow.

    Returns the opened PIL Image (in RGB mode) on success.

    Raises
    ------
    ImageValidationError
        If the image cannot be opened or verified.
    UnsupportedFormatError
        If the image format (detected by Pillow) is not allowed.
    """
    try:
        img = Image.open(io.BytesIO(data))
    except Exception as exc:
        raise ImageValidationError(
            "Cannot open file as an image.", detail=str(exc)
        ) from exc

    # Verify image integrity
    try:
        img_copy = img.copy()
        img_copy.verify()
    except Exception as exc:
        raise ImageValidationError(
            "Image file is corrupted or incomplete.", detail=str(exc)
        ) from exc

    # Check format
    if img.format and img.format not in ALLOWED_PILLOW_FORMATS:
        raise UnsupportedFormatError(
            f"Detected image format '{img.format}' is not supported."
        )

    # Convert to RGB
    try:
        if img.mode != "RGB":
            img = img.convert("RGB")
    except Exception as exc:
        raise ImageValidationError(
            "Cannot convert image to RGB.", detail=str(exc)
        ) from exc

    return img


def validate_upload(
    data: bytes,
    filename: str,
    max_bytes: int,
) -> Tuple[Image.Image, str]:
    """
    Full validation pipeline for an uploaded image.

    Parameters
    ----------
    data : bytes
        Raw file content.
    filename : str
        Original filename from the upload.
    max_bytes : int
        Maximum allowed file size in bytes.

    Returns
    -------
    (Image.Image, str)
        The validated PIL Image (RGB) and the lowercase extension.

    Raises
    ------
    FileTooLargeError, UnsupportedFormatError, ImageValidationError
    """
    ext = validate_file_extension(filename)
    validate_file_size(data, max_bytes)
    img = validate_image_content(data)
    return img, ext
