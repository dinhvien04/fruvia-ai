"""
Rate limiting and concurrency control middleware.

Provides an abstract BaseRateLimiter interface allowing single-instance
in-memory rate limiting with future seamless Redis / Distributed backends.
"""

from __future__ import annotations

import abc
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


class BaseRateLimiter(abc.ABC):
    """Abstract interface for rate limiters."""

    @abc.abstractmethod
    def check_rate_limit(
        self, client_key: str, limit: int, window_seconds: float = 60.0
    ) -> tuple[bool, int]:
        """
        Check if request is allowed under rate limit.

        Parameters
        ----------
        client_key : str
            Unique client identifier (e.g. IP address or API token).
        limit : int
            Max permitted requests per window.
        window_seconds : float
            Window length in seconds.

        Returns
        -------
        tuple[bool, int]
            (is_allowed, remaining_requests)
        """
        ...


class InMemorySlidingWindowRateLimiter(BaseRateLimiter):
    """
    In-memory rate limiter using sliding timestamp windows.
    Suitable for single-instance deployments.
    """

    def __init__(self) -> None:
        self.requests: dict[str, list[float]] = defaultdict(list)

    def check_rate_limit(
        self, client_key: str, limit: int, window_seconds: float = 60.0
    ) -> tuple[bool, int]:
        now = time.time()
        window_start = now - window_seconds

        # Prune older timestamps
        self.requests[client_key] = [t for t in self.requests[client_key] if t > window_start]

        count = len(self.requests[client_key])
        if count >= limit:
            return False, 0

        self.requests[client_key].append(now)
        remaining = max(0, limit - count - 1)
        return True, remaining


_global_rate_limiter: BaseRateLimiter | None = None


def get_rate_limiter() -> BaseRateLimiter:
    """Return singleton rate limiter backend instance."""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = InMemorySlidingWindowRateLimiter()
    return _global_rate_limiter


def extract_client_ip(request: Request) -> str:
    """
    Extract the real client IP address safely without allowing header spoofing.

    Security model:
    - By default (`trust_proxy_headers=False`), uses `request.client.host`.
    - `X-Forwarded-For` is only inspected if `trust_proxy_headers=True` AND
      the immediate connecting peer (`request.client.host`) is in `trusted_proxy_ips`.
    - Handles multiple comma-separated IPs deterministically.
    """
    settings = get_settings()
    peer_ip = request.client.host if request.client else "127.0.0.1"

    if not settings.trust_proxy_headers:
        return peer_ip

    # If proxy trust is enabled, verify the immediate peer is a trusted proxy
    trusted_set = settings.trusted_proxy_ip_list
    if trusted_set and peer_ip not in trusted_set:
        # Peer is not trusted; ignore forwarded headers
        return peer_ip

    forwarded_header = request.headers.get("X-Forwarded-For", "").strip()
    if not forwarded_header:
        return peer_ip

    # Parse comma-separated IPs and take the client IP (first non-empty entry)
    ips = [ip.strip() for ip in forwarded_header.split(",") if ip.strip()]
    if not ips:
        return peer_ip

    return ips[0]


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiter middleware for API endpoints.
    Protects POST /api/retrieve from traffic surges.
    """

    def __init__(self, app: Any, limiter: BaseRateLimiter | None = None) -> None:
        super().__init__(app)
        self.limiter = limiter or get_rate_limiter()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Only rate limit POST /api/retrieve
        if request.method == "POST" and request.url.path.endswith("/retrieve"):
            settings = get_settings()
            client_ip = extract_client_ip(request)

            is_allowed, remaining = self.limiter.check_rate_limit(
                client_key=client_ip,
                limit=settings.rate_limit_per_minute,
                window_seconds=60.0,
            )

            if not is_allowed:
                logger.warning("Rate limit exceeded for client: %s", client_ip)
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": True,
                        "error_code": "RATE_LIMIT_EXCEEDED",
                        "message": "Too many requests. Please try again in a minute.",
                        "detail": f"Rate limit of {settings.rate_limit_per_minute} req/min exceeded.",
                    },
                    headers={
                        "Retry-After": "60",
                        "X-RateLimit-Limit": str(settings.rate_limit_per_minute),
                        "X-RateLimit-Remaining": "0",
                    },
                )

            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(settings.rate_limit_per_minute)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            return response

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
