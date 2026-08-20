"""
Fruvia AI FastAPI application entry point.

This module creates the FastAPI app instance, registers middleware,
exception handlers, and routes. Model loading happens at startup.
Serves frontend web application static files for single-domain deployment.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.exceptions import FruviaError, fruvia_error_handler, generic_error_handler
from app.core.logging import get_logger, setup_logging
from app.ml.image_encoder import get_image_encoder
from app.repositories.qdrant_repository import get_qdrant_repository

logger = get_logger(__name__)

# Resolve frontend directory path safely relative to backend project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — startup and shutdown logic."""
    settings = get_settings()
    setup_logging(level=settings.log_level, env=settings.app_env)
    logger.info(
        "Fruvia AI starting — env=%s, version=%s",
        settings.app_env,
        settings.app_version,
    )

    # Initialize ImageEncoder
    try:
        encoder = get_image_encoder()
        encoder.load_model()
        app.state.image_encoder = encoder
    except Exception as e:
        logger.warning("Failed to initialize ImageEncoder during startup: %s", e)

    # Initialize QdrantRepository
    try:
        qdrant_repo = get_qdrant_repository()
        if qdrant_repo.is_connected():
            logger.info("Connected to Qdrant Cloud.")
        else:
            logger.warning("Qdrant Cloud is not reachable during startup.")
        app.state.qdrant_repo = qdrant_repo
    except Exception as e:
        logger.warning("Failed to initialize QdrantRepository during startup: %s", e)

    yield

    logger.info("Fruvia AI shutting down.")


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()

    app = FastAPI(
        title="Fruvia AI",
        description="AI-powered fruit recognition and image retrieval",
        version=settings.app_version,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # --- Middleware ---
    from app.core.middleware import RequestIdMiddleware
    from app.core.rate_limit import RateLimitMiddleware

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Exception handlers ---
    app.add_exception_handler(FruviaError, fruvia_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, generic_error_handler)  # type: ignore[arg-type]

    # --- API Routes ---
    from app.api.routes_health import router as health_router
    from app.api.routes_retrieval import router as retrieval_router

    app.include_router(health_router, prefix="/api")
    app.include_router(retrieval_router, prefix="/api")

    # --- Serve Frontend Web Application Pages & Static Assets ---
    if FRONTEND_DIR.exists():
        # Clean URL page routes
        @app.get("/", include_in_schema=False)
        async def serve_homepage() -> FileResponse:
            return FileResponse(FRONTEND_DIR / "index.html")

        @app.get("/search", include_in_schema=False)
        async def serve_search_page() -> FileResponse:
            return FileResponse(FRONTEND_DIR / "retrieval.html")

        # Compatibility redirects for .html paths
        @app.get("/index.html", include_in_schema=False)
        async def redirect_index() -> RedirectResponse:
            return RedirectResponse(url="/", status_code=301)

        @app.get("/retrieval.html", include_in_schema=False)
        async def redirect_retrieval() -> RedirectResponse:
            return RedirectResponse(url="/search", status_code=301)

        # SEO files
        @app.get("/robots.txt", include_in_schema=False)
        async def serve_robots() -> FileResponse:
            return FileResponse(FRONTEND_DIR / "robots.txt")

        @app.get("/sitemap.xml", include_in_schema=False)
        async def serve_sitemap() -> FileResponse:
            return FileResponse(FRONTEND_DIR / "sitemap.xml")

        @app.get("/favicon.svg", include_in_schema=False)
        async def serve_favicon() -> FileResponse:
            return FileResponse(FRONTEND_DIR / "favicon.svg")

        # Static assets directories
        if (FRONTEND_DIR / "css").exists():
            app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
        if (FRONTEND_DIR / "js").exists():
            app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")
        if (FRONTEND_DIR / "assets").exists():
            app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

    return app


app = create_app()
