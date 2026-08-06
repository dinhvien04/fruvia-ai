"""
Image validation utilities with strict security safeguards.

Validates uploaded images by:
- Enforcing bounded chunked reading to prevent RAM exhaustion
- Checking file extension, Content-Type, and Pillow detected format consistency
- Setting Pillow pixel limits to prevent decompression bomb attacks
- Verifying image resolution (width/height bounds)
- Executing proper Pillow verify() on the initial stream and re-opening to convert to RGB
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

from PIL import Image

from app.core.config import get_settings
from app.core.exceptions import (
    FileTooLargeError,
    ImageValidationError,
    UnsupportedFormatError,
)

if TYPE_CHECKING:
    from fastapi import UploadFile

# Allowed file extensions (lowercase)
ALLOWED_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png", ".webp"}

# Pillow format names that correspond to allowed types
ALLOWED_PILLOW_FORMATS: set[str] = {"JPEG", "PNG", "WEBP"}

# MIME types considered valid
ALLOWED_MIME_TYPES: set[str] = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}

# Map extensions to expected Pillow formats
EXT_TO_PILLOW_FORMAT: dict[str, str] = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}

# Map Content-Types to expected Pillow formats
MIME_TO_PILLOW_FORMAT: dict[str, str] = {
    "image/jpeg": "JPEG",
    "image/jpg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
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
    Ensure raw bytes payload does not exceed max_bytes limit.

    Raises
    ------
    FileTooLargeError
        If len(data) > max_bytes.
    """
    if len(data) > max_bytes:
        max_mb = max_bytes / (1024 * 1024)
        actual_mb = len(data) / (1024 * 1024)
        raise FileTooLargeError(f"File size {actual_mb:.1f} MB exceeds the {max_mb:.0f} MB limit.")


async def read_upload_bounded(upload_file: UploadFile, max_bytes: int) -> bytes:
    """
    Read upload file stream in 64 KiB chunks up to max_bytes + 1.

    Prevents RAM exhaustion by raising FileTooLargeError as soon as accumulated
    bytes exceed max_bytes.

    Parameters
    ----------
    upload_file : UploadFile
        FastAPI UploadFile instance.
    max_bytes : int
        Maximum allowed size in bytes.

    Returns
    -------
    bytes
        Accumulated raw file bytes.

    Raises
    ------
    FileTooLargeError
        If total payload exceeds max_bytes.
    """
    chunk_size = 64 * 1024  # 64 KiB chunks
    accumulated = bytearray()

    while True:
        chunk = await upload_file.read(chunk_size)
        if not chunk:
            break
        accumulated.extend(chunk)
        if len(accumulated) > max_bytes:
            max_mb = max_bytes / (1024 * 1024)
            raise FileTooLargeError(
                f"Uploaded file exceeds the maximum allowed limit of {max_mb:.0f} MB."
            )

    return bytes(accumulated)


def validate_image_content(
    data: bytes,
    content_type: str | None = None,
    filename: str | None = None,
) -> Image.Image:
    """
    Open, verify, and validate image data using Pillow with security limits.

    Checks:
    - Protection against decompression bomb (Image.MAX_IMAGE_PIXELS)
    - Image integrity check via img.verify() on original stream
    - Re-open fresh stream to load pixels and check width/height limits
    - Consistency check across filename extension, Content-Type, and detected format

    Returns
    -------
    Image.Image
        The validated PIL Image instance converted to RGB mode.

    Raises
    ------
    ImageValidationError
        If file cannot be opened, is corrupted, or exceeds pixel/dimension limits.
    UnsupportedFormatError
        If image format is disallowed or inconsistent.
    """
    settings = get_settings()

    # Decompression bomb prevention
    Image.MAX_IMAGE_PIXELS = settings.max_image_pixels

    # Step 1: Open stream and verify image integrity directly
    try:
        stream_orig = io.BytesIO(data)
        img_orig = Image.open(stream_orig)
        detected_format = img_orig.format
        img_orig.verify()
    except Image.DecompressionBombError as exc:
        raise ImageValidationError(
            "Image pixel count exceeds maximum allowed limit (Decompression Bomb protection).",
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise ImageValidationError(
            "Cannot open file as a valid image or file is corrupted.",
            detail=str(exc),
        ) from exc

    # Step 2: Validate detected Pillow format
    if not detected_format or detected_format not in ALLOWED_PILLOW_FORMATS:
        raise UnsupportedFormatError(
            f"Detected image format '{detected_format}' is not supported. "
            f"Allowed formats: {', '.join(sorted(ALLOWED_PILLOW_FORMATS))}"
        )

    # Step 3: Check consistency between extension, MIME type, and detected format
    if filename:
        ext = ""
        if "." in filename:
            ext = "." + filename.rsplit(".", 1)[-1].lower()
        expected_fmt_ext = EXT_TO_PILLOW_FORMAT.get(ext)
        if expected_fmt_ext and expected_fmt_ext != detected_format:
            raise UnsupportedFormatError(
                f"File extension '{ext}' does not match detected image format '{detected_format}'."
            )

    if content_type:
        mime_clean = content_type.lower().split(";")[0].strip()
        if mime_clean in ALLOWED_MIME_TYPES:
            expected_fmt_mime = MIME_TO_PILLOW_FORMAT.get(mime_clean)
            if expected_fmt_mime and expected_fmt_mime != detected_format:
                raise UnsupportedFormatError(
                    f"Content-Type '{content_type}' does not match detected image format '{detected_format}'."
                )

    # Step 4: Re-open fresh stream to load image pixel data and validate dimensions
    try:
        stream_fresh = io.BytesIO(data)
        img_load = Image.open(stream_fresh)
        img_load.load()

        width, height = img_load.size
        if width > settings.max_image_width or height > settings.max_image_height:
            raise ImageValidationError(
                f"Image dimensions ({width}x{height}) exceed maximum allowed limits "
                f"({settings.max_image_width}x{settings.max_image_height})."
            )

        if width * height > settings.max_image_pixels:
            raise ImageValidationError(
                f"Image total pixels ({width * height}) exceed maximum allowed limit "
                f"({settings.max_image_pixels})."
            )

        # Convert to RGB
        if img_load.mode != "RGB":
            img_load = img_load.convert("RGB")

        return img_load

    except ImageValidationError:
        raise
    except Exception as exc:
        raise ImageValidationError(
            "Failed to load or process image pixel data.",
            detail=str(exc),
        ) from exc


def validate_upload(
    data: bytes,
    filename: str,
    max_bytes: int,
    content_type: str | None = None,
) -> tuple[Image.Image, str]:
    """
    Full validation pipeline for an uploaded image payload.

    Parameters
    ----------
    data : bytes
        Raw file payload.
    filename : str
        Original filename.
    max_bytes : int
        Maximum size limit in bytes.
    content_type : str | None
        HTTP Content-Type header.

    Returns
    -------
    (Image.Image, str)
        The validated PIL Image (RGB) and lowercase extension.
    """
    ext = validate_file_extension(filename)
    validate_file_size(data, max_bytes)
    img = validate_image_content(data, content_type=content_type, filename=filename)
    return img, ext
