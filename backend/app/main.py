"""
Fruvia AI FastAPI application entry point.

This module creates the FastAPI app instance, registers middleware,
exception handlers, and routes. Model loading happens at startup.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import FruviaError, fruvia_error_handler, generic_error_handler
from app.core.logging import get_logger, setup_logging
from app.ml.image_encoder import get_image_encoder
from app.repositories.qdrant_repository import get_qdrant_repository

logger = get_logger(__name__)


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

    # --- CORS ---
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

    # --- Routes ---
    from app.api.routes_health import router as health_router
    from app.api.routes_retrieval import router as retrieval_router

    app.include_router(health_router, prefix="/api")
    app.include_router(retrieval_router, prefix="/api")

    return app


app = create_app()
