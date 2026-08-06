"""
Fruvia AI structured logging.

Uses stdlib logging with JSON-like formatting for production
and human-readable formatting for development.
"""

from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar

# Context variable for per-request ID tracking
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def generate_request_id() -> str:
    """Generate a short unique request ID."""
    return uuid.uuid4().hex[:12]


class RequestIdFilter(logging.Filter):
    """Inject request_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        from app.core.middleware import get_request_id

        record.request_id = get_request_id() or "-"  # type: ignore[attr-defined]
        return True


def setup_logging(level: str = "INFO", env: str = "development") -> None:
    """
    Configure the root logger for the application.

    Parameters
    ----------
    level : str
        Logging level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    env : str
        Environment name. 'production' uses a structured format;
        everything else uses a human-readable format.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    if env == "production":
        fmt = (
            '{"timestamp":"%(asctime)s","level":"%(levelname)s",'
            '"request_id":"%(request_id)s","name":"%(name)s",'
            '"message":"%(message)s"}'
        )
    else:
        fmt = "%(asctime)s | %(levelname)-8s | %(request_id)s | %(name)s | %(message)s"

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S"))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(numeric_level)

    # Quiet noisy third-party loggers
    for name in ("uvicorn.access", "httpcore", "httpx", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger that inherits the application config."""
    return logging.getLogger(name)
