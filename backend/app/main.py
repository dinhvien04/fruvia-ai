"""
Fruvia AI FastAPI application entry point.

This module creates the FastAPI app instance, registers middleware,
exception handlers, and routes. Model loading happens at startup.

NOTE: Full route registration and model loading will be implemented
in Phase 5. This stub provides the app factory and health endpoint
for testing the project skeleton.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import FruviaError, generic_error_handler, fruvia_error_handler
from app.core.logging import get_logger, setup_logging

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
    # Phase 5: load classifier model and connect to Qdrant here
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

    # --- Routes (Phase 5 will add classify, retrieve, fruits) ---
    from app.api.routes_health import router as health_router

    app.include_router(health_router, prefix="/api")

    return app


app = create_app()
