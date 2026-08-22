"""
Image validation utilities with strict security safeguards.

Validates uploaded images by:
- Enforcing bounded chunked reading to prevent RAM exhaustion
- Restricting Pillow decoders strictly to JPEG, PNG, and WEBP to prevent unverified decoder exploits
- Setting Pillow pixel limits and catching decompression bomb warnings/errors to fail closed
- Verifying image resolution (width/height bounds) BEFORE performing full pixel decode/load
- Checking file extension, Content-Type, and Pillow detected format consistency
- Executing proper Pillow verify() on the initial stream and re-opening to convert to RGB
"""

from __future__ import annotations

import io
import warnings
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

# Maximum allowed filename length to prevent filesystem/buffer abuse
MAX_FILENAME_LENGTH: int = 255

# Allowed file extensions (lowercase)
ALLOWED_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png", ".webp"}

# Pillow format names that correspond to allowed types
ALLOWED_PILLOW_FORMATS: list[str] = ["JPEG", "PNG", "WEBP"]
ALLOWED_PILLOW_FORMAT_SET: set[str] = set(ALLOWED_PILLOW_FORMATS)

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
    Check the file extension is in the allowed set and filename length is bounded.

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
    ImageValidationError
        If filename is missing or exceeds max length.
    UnsupportedFormatError
        If the extension is not allowed.
    """
    if not filename or not filename.strip():
        raise ImageValidationError("Filename cannot be empty.")

    if len(filename) > MAX_FILENAME_LENGTH:
        raise ImageValidationError(
            f"Filename length ({len(filename)}) exceeds maximum allowed limit of {MAX_FILENAME_LENGTH} characters."
        )

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
    Ensure raw bytes payload is non-empty and does not exceed max_bytes limit.

    Raises
    ------
    ImageValidationError
        If data is empty (0 bytes).
    FileTooLargeError
        If len(data) > max_bytes.
    """
    if not data or len(data) == 0:
        raise ImageValidationError("Uploaded image file is empty (0 bytes).")

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
    Open, verify, and validate image data using Pillow with strict security limits.

    Safeguards:
    - Decoders strictly limited to ALLOWED_PILLOW_FORMATS (JPEG, PNG, WEBP)
    - Protection against decompression bomb (Image.MAX_IMAGE_PIXELS + warning capture)
    - Image integrity check via img.verify() on original stream
    - Geometry checks (width > 0, height > 0, width/height bounds, total pixels) BEFORE full load
    - Re-open fresh stream to load pixels and convert to RGB mode
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
    if not data or len(data) == 0:
        raise ImageValidationError("Uploaded image data is empty.")

    settings = get_settings()

    # Decompression bomb prevention policy
    Image.MAX_IMAGE_PIXELS = settings.max_image_pixels

    # Step 1: Open stream with restricted decoders and verify integrity
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            stream_orig = io.BytesIO(data)
            # Restrict decoders strictly to JPEG, PNG, WEBP
            img_orig = Image.open(stream_orig, formats=ALLOWED_PILLOW_FORMATS)
            detected_format = img_orig.format
            img_orig.verify()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageValidationError(
            "Image pixel count exceeds maximum allowed limit (Decompression Bomb protection)."
        ) from exc
    except Exception as exc:
        raise ImageValidationError(
            "Cannot open file as a valid image or file is corrupted."
        ) from exc

    # Step 2: Validate detected Pillow format
    if not detected_format or detected_format not in ALLOWED_PILLOW_FORMAT_SET:
        raise UnsupportedFormatError(
            f"Detected image format '{detected_format}' is not supported. "
            f"Allowed formats: {', '.join(sorted(ALLOWED_PILLOW_FORMAT_SET))}"
        )

    # Step 3: Check consistency between extension, MIME type, and detected format
    if filename:
        ext = ""
        if "." in filename:
            ext = "." + filename.rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise UnsupportedFormatError(
                f"File extension '{ext}' is not supported. "
                f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )
        expected_fmt_ext = EXT_TO_PILLOW_FORMAT.get(ext)
        if expected_fmt_ext and expected_fmt_ext != detected_format:
            raise UnsupportedFormatError(
                f"File extension '{ext}' does not match detected image format '{detected_format}'."
            )

    if content_type:
        mime_clean = content_type.lower().split(";")[0].strip()
        if mime_clean not in ALLOWED_MIME_TYPES:
            raise UnsupportedFormatError(
                f"Content-Type '{content_type}' is not supported. "
                f"Allowed MIME types: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
            )
        expected_fmt_mime = MIME_TO_PILLOW_FORMAT.get(mime_clean)
        if expected_fmt_mime and expected_fmt_mime != detected_format:
            raise UnsupportedFormatError(
                f"Content-Type '{content_type}' does not match detected image format '{detected_format}'."
            )

    # Step 4: Re-open fresh stream with restricted decoders, check dimensions BEFORE load
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            stream_fresh = io.BytesIO(data)
            img_load = Image.open(stream_fresh, formats=ALLOWED_PILLOW_FORMATS)

            width, height = img_load.size
            if width <= 0 or height <= 0:
                raise ImageValidationError(
                    f"Invalid image dimensions ({width}x{height}). Width and height must be positive."
                )

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

            # Only after geometry validation passes, load pixel buffer into memory
            img_load.load()

            # Convert to RGB
            if img_load.mode != "RGB":
                img_load = img_load.convert("RGB")

            return img_load

    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageValidationError(
            "Image pixel count exceeds maximum allowed limit (Decompression Bomb protection)."
        ) from exc
    except ImageValidationError:
        raise
    except Exception as exc:
        raise ImageValidationError("Failed to load or process image pixel data.") from exc


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
