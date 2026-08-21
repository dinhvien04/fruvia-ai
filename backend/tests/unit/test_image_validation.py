"""
Unit tests for image validation utilities.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.core.exceptions import (
    FileTooLargeError,
    ImageValidationError,
    UnsupportedFormatError,
)
from app.utils.image_validation import (
    validate_file_extension,
    validate_file_size,
    validate_image_content,
    validate_upload,
)

pytestmark = pytest.mark.unit


# ================================================================
# validate_file_extension
# ================================================================


class TestValidateFileExtension:
    """Tests for file extension validation."""

    @pytest.mark.parametrize(
        "filename,expected",
        [
            ("photo.jpg", ".jpg"),
            ("photo.JPEG", ".jpeg"),
            ("image.png", ".png"),
            ("image.PNG", ".png"),
            ("pic.webp", ".webp"),
        ],
    )
    def test_valid_extensions(self, filename: str, expected: str) -> None:
        assert validate_file_extension(filename) == expected

    @pytest.mark.parametrize(
        "filename",
        [
            "file.gif",
            "file.bmp",
            "file.tiff",
            "file.svg",
            "file.txt",
            "file.pdf",
            "noextension",
        ],
    )
    def test_invalid_extensions(self, filename: str) -> None:
        with pytest.raises(UnsupportedFormatError):
            validate_file_extension(filename)

    def test_empty_filename(self) -> None:
        with pytest.raises(ImageValidationError, match="Filename cannot be empty"):
            validate_file_extension("")


# ================================================================
# validate_file_size
# ================================================================


class TestValidateFileSize:
    """Tests for file size validation."""

    def test_under_limit(self) -> None:
        data = b"\x00" * 1000
        validate_file_size(data, max_bytes=2000)  # Should not raise

    def test_at_limit(self) -> None:
        data = b"\x00" * 2000
        validate_file_size(data, max_bytes=2000)  # Should not raise

    def test_over_limit(self) -> None:
        data = b"\x00" * 2001
        with pytest.raises(FileTooLargeError):
            validate_file_size(data, max_bytes=2000)

    def test_empty_file(self) -> None:
        with pytest.raises(ImageValidationError, match="Uploaded image file is empty"):
            validate_file_size(b"", max_bytes=1000)


# ================================================================
# validate_image_content
# ================================================================


class TestValidateImageContent:
    """Tests for image content validation."""

    def test_valid_jpeg(self, sample_jpg_bytes: bytes) -> None:
        img = validate_image_content(sample_jpg_bytes)
        assert img.mode == "RGB"
        assert img.size == (100, 100)

    def test_valid_png(self, sample_png_bytes: bytes) -> None:
        img = validate_image_content(sample_png_bytes)
        assert img.mode == "RGB"

    def test_rgba_converted_to_rgb(self) -> None:
        rgba = Image.new("RGBA", (50, 50), color=(255, 0, 0, 128))
        buf = io.BytesIO()
        rgba.save(buf, format="PNG")
        img = validate_image_content(buf.getvalue())
        assert img.mode == "RGB"

    def test_extension_content_type_mismatch_raises(self, sample_jpg_bytes: bytes) -> None:
        """Uploading JPEG content with .png extension should raise UnsupportedFormatError."""
        with pytest.raises(UnsupportedFormatError, match="does not match detected"):
            validate_image_content(sample_jpg_bytes, content_type="image/jpeg", filename="test.png")

    def test_content_type_mismatch_raises(self, sample_jpg_bytes: bytes) -> None:
        """Uploading JPEG content with image/png content-type header should raise UnsupportedFormatError."""
        with pytest.raises(UnsupportedFormatError, match="does not match detected"):
            validate_image_content(sample_jpg_bytes, content_type="image/png", filename="test.jpg")

    def test_corrupt_image_raises(self, corrupt_image_bytes: bytes) -> None:
        with pytest.raises(ImageValidationError):
            validate_image_content(corrupt_image_bytes)

    def test_non_image_raises(self, non_image_bytes: bytes) -> None:
        with pytest.raises(ImageValidationError):
            validate_image_content(non_image_bytes)


# ================================================================
# validate_upload (full pipeline)
# ================================================================


class TestValidateUpload:
    """Tests for the complete upload validation pipeline."""

    def test_valid_jpeg_upload(self, sample_jpg_bytes: bytes) -> None:
        img, ext = validate_upload(sample_jpg_bytes, "photo.jpg", max_bytes=10 * 1024 * 1024)
        assert img.mode == "RGB"
        assert ext == ".jpg"

    def test_valid_png_upload(self, sample_png_bytes: bytes) -> None:
        img, ext = validate_upload(sample_png_bytes, "photo.png", max_bytes=10 * 1024 * 1024)
        assert img.mode == "RGB"
        assert ext == ".png"

    def test_wrong_extension_rejected(self, sample_jpg_bytes: bytes) -> None:
        with pytest.raises(UnsupportedFormatError):
            validate_upload(sample_jpg_bytes, "photo.gif", max_bytes=10 * 1024 * 1024)

    def test_oversized_rejected(self, sample_jpg_bytes: bytes) -> None:
        with pytest.raises(FileTooLargeError):
            validate_upload(sample_jpg_bytes, "photo.jpg", max_bytes=10)  # 10 bytes limit

    def test_corrupt_image_rejected(self, corrupt_image_bytes: bytes) -> None:
        with pytest.raises(ImageValidationError):
            validate_upload(corrupt_image_bytes, "photo.jpg", max_bytes=10 * 1024 * 1024)
