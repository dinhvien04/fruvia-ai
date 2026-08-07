"""
Rate limiting and concurrency control middleware.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple in-memory IP rate limiter for API endpoints.
    Tracks request timestamps in sliding 60-second windows.
    """

    def __init__(self, app: Any) -> None:  # type: ignore[name-defined]
        super().__init__(app)
        self.requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Only rate limit POST /api/retrieve
        if request.method == "POST" and request.url.path.endswith("/retrieve"):
            settings = get_settings()
            client_ip = request.client.host if request.client else "127.0.0.1"
            now = time.time()
            window_start = now - 60.0

            # Prune old timestamps
            self.requests[client_ip] = [t for t in self.requests[client_ip] if t > window_start]

            if len(self.requests[client_ip]) >= settings.rate_limit_per_minute:
                logger.warning("Rate limit exceeded for IP: %s", client_ip)
                return JSONResponse(
                    status_code=429,
                    content={
                        "error_code": "RATE_LIMIT_EXCEEDED",
                        "message": "Too many requests. Please try again in a minute.",
                        "detail": f"Rate limit of {settings.rate_limit_per_minute} req/min exceeded.",
                    },
                )

            self.requests[client_ip].append(now)

        return await call_next(request)


class ConcurrencyLimiter:
    """
    Global asyncio semaphore to limit concurrent heavy ML model inference calls.
    Prevents server OOM during request surges.
    """

    def __init__(self, max_concurrent: int = 4) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def run(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        async with self._semaphore:
            return await func(*args, **kwargs)


_concurrency_limiter: ConcurrencyLimiter | None = None


def get_concurrency_limiter() -> ConcurrencyLimiter:
    global _concurrency_limiter
    if _concurrency_limiter is None:
        settings = get_settings()
        _concurrency_limiter = ConcurrencyLimiter(settings.max_concurrent_inferences)
    return _concurrency_limiter
