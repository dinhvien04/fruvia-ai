"""
Custom ASGI middlewares for request tracing, body size limits, and security headers.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

request_id_ctx_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """Return the current request ID from context variable."""
    return request_id_ctx_var.get()


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware that extracts or generates a unique X-Request-ID for each HTTP request,
    stores it in a ContextVar for logger context, and returns it in response headers.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_ctx_var.set(req_id)

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            request_id_ctx_var.reset(token)


class RequestBodyLimitMiddleware:
    """
    Pure ASGI middleware that enforces raw HTTP request body limits BEFORE multipart/form-data parsing.

    Features:
    - Inspects Content-Length header immediately and rejects with 413 if it exceeds max_bytes.
    - Wraps the ASGI receive() callable to count actual streaming body chunks.
    - Fails closed with HTTP 413 if cumulative received body bytes exceed max_bytes.
    - Never buffers the entire payload in memory.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        content_length_header = headers.get("content-length")

        if content_length_header is not None:
            try:
                content_length = int(content_length_header)
                if content_length > self.max_bytes:
                    max_mb = self.max_bytes / (1024 * 1024)
                    resp = JSONResponse(
                        status_code=413,
                        content={
                            "error": "FILE_TOO_LARGE",
                            "message": f"Request body size exceeds the maximum allowed limit of {max_mb:.0f} MB.",
                        },
                    )
                    await resp(scope, receive, send)
                    return
            except ValueError:
                pass  # If Content-Length is non-numeric, fallback to streaming byte count

        received_bytes = 0

        async def limited_receive() -> dict:
            nonlocal received_bytes
            message = await receive()

            if message.get("type") == "http.request":
                body_chunk = message.get("body", b"")
                received_bytes += len(body_chunk)

                if received_bytes > self.max_bytes:
                    max_mb = self.max_bytes / (1024 * 1024)
                    raise RequestBodyTooLargeError(
                        f"Streaming request body exceeded limit of {max_mb:.0f} MB."
                    )

            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyTooLargeError:
            max_mb = self.max_bytes / (1024 * 1024)
            resp = JSONResponse(
                status_code=413,
                content={
                    "error": "FILE_TOO_LARGE",
                    "message": f"Request body size exceeds the maximum allowed limit of {max_mb:.0f} MB.",
                },
            )
            await resp(scope, receive, send)


class RequestBodyTooLargeError(Exception):
    """Internal exception raised when ASGI stream body exceeds configured byte limit."""


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to inject strict production HTTP security response headers:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - Referrer-Policy: strict-origin-when-cross-origin
    - Permissions-Policy: camera=(), microphone=(), geolocation=()
    - Content-Security-Policy: strict defense-in-depth policy
    - Strict-Transport-Security: optional production HTTPS HSTS
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        from app.core.config import get_settings

        settings = get_settings()
        response = await call_next(request)

        # Baseline security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        # Build CSP directives
        img_src_hosts = ["'self'", "data:"]
        for host in settings.allowed_image_host_list:
            if host.startswith("http://") or host.startswith("https://"):
                img_src_hosts.append(host)
            else:
                img_src_hosts.append(f"https://{host}")

        connect_src_hosts = ["'self'"]
        for origin in settings.csp_connect_origin_list:
            connect_src_hosts.append(origin)
        for origin in settings.cors_origin_list:
            if origin != "*":
                connect_src_hosts.append(origin)

        csp_policy = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            f"img-src {' '.join(img_src_hosts)}; "
            f"connect-src {' '.join(sorted(set(connect_src_hosts)))}; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self';"
        )
        response.headers["Content-Security-Policy"] = csp_policy

        # HSTS only when explicitly enabled (production HTTPS)
        if settings.enable_hsts and settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response
