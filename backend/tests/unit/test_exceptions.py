"""
Unit tests for exception hierarchy.
"""

from __future__ import annotations

import pytest

from app.core.exceptions import (
    FileTooLargeError,
    FruviaError,
    ImageValidationError,
    LowConfidenceError,
    ModelNotLoadedError,
    QdrantConnectionError,
    UnsupportedFormatError,
)

pytestmark = pytest.mark.unit


class TestExceptionHierarchy:
    """All domain errors should extend FruviaError."""

    @pytest.mark.parametrize("exc_class,code,status", [
        (ImageValidationError, "INVALID_IMAGE", 400),
        (FileTooLargeError, "FILE_TOO_LARGE", 413),
        (UnsupportedFormatError, "UNSUPPORTED_FORMAT", 415),
        (ModelNotLoadedError, "MODEL_NOT_LOADED", 503),
        (QdrantConnectionError, "QDRANT_UNAVAILABLE", 503),
        (LowConfidenceError, "LOW_CONFIDENCE", 200),
    ])
    def test_error_attributes(
        self, exc_class: type, code: str, status: int
    ) -> None:
        err = exc_class()
        assert isinstance(err, FruviaError)
        assert err.error_code == code
        assert err.status_code == status

    def test_custom_message(self) -> None:
        err = ImageValidationError("Custom message")
        assert err.message == "Custom message"
        assert str(err) == "Custom message"

    def test_to_dict(self) -> None:
        err = FileTooLargeError("Too big")
        d = err.to_dict()
        assert d["error"] is True
        assert d["error_code"] == "FILE_TOO_LARGE"
        assert d["message"] == "Too big"

    def test_detail_not_in_dict(self) -> None:
        """Internal detail must NOT leak to client via to_dict()."""
        err = ImageValidationError("Bad image", detail="PIL traceback here")
        d = err.to_dict()
        assert "detail" not in d
        assert "PIL traceback" not in d["message"]
