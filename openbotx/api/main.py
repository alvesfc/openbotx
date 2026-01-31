"""FastAPI application for OpenBotX."""

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from openbotx.api.routes import (
    logs,
    media,
    memory,
    messages,
    providers,
    scheduler,
    skills,
    system,
    tools,
)
from openbotx.core.orchestrator import get_orchestrator
from openbotx.helpers.logger import get_logger
from openbotx.version import __version__

logger = get_logger("api")

# Store startup time
_startup_time: float = 0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    from openbotx.helpers.config import get_config
    from openbotx.helpers.gateway_loader import initialize_gateways, stop_all_gateways

    global _startup_time
    _startup_time = time.time()

    logger.info("api_starting")

    # Load config
    config = get_config()

    # Initialize all providers (storage, transcription, etc.)
    from openbotx.helpers.provider_loader import (
        initialize_providers,
        stop_all_providers,
    )

    await initialize_providers(config)

    # Initialize orchestrator
    from openbotx.core.orchestrator import get_orchestrator

    orchestrator = get_orchestrator()
    await orchestrator.initialize()
    await orchestrator.start()

    # Initialize all enabled gateways
    await initialize_gateways(
        config=config,
        message_handler=lambda msg: orchestrator.enqueue_message(msg),
    )

    logger.info("api_started")

    yield

    # Shutdown
    logger.info("api_stopping")
    await stop_all_gateways()
    await orchestrator.stop()
    await stop_all_providers()
    logger.info("api_stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="OpenBotX API",
        description="Personal AI Assistant",
        version=__version__,
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(messages.router, prefix="/api/messages", tags=["messages"])
    app.include_router(skills.router, prefix="/api/skills", tags=["skills"])
    app.include_router(tools.router, prefix="/api/tools", tags=["tools"])
    app.include_router(providers.router, prefix="/api/providers", tags=["providers"])
    app.include_router(scheduler.router, prefix="/api/scheduler", tags=["scheduler"])
    app.include_router(memory.router, prefix="/api/memory", tags=["memory"])
    app.include_router(media.router, prefix="/api/media", tags=["media"])
    app.include_router(logs.router, prefix="/api/logs", tags=["logs"])
    app.include_router(system.router, prefix="/api/system", tags=["system"])

    # Error handlers
    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        """Handle HTTP exceptions."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": exc.detail,
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """Handle general exceptions."""
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            error=str(exc),
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "Internal server error",
            },
        )

    # Root endpoint
    @app.get("/")
    async def root() -> dict[str, Any]:
        """Root endpoint."""
        return {
            "name": "OpenBotX API",
            "version": __version__,
            "status": "running",
        }

    # Health check
    @app.get("/health")
    async def health() -> dict[str, Any]:
        """Health check endpoint."""
        orchestrator = get_orchestrator()
        return {
            "status": "healthy" if orchestrator.is_running else "unhealthy",
            "version": __version__,
            "uptime_seconds": time.time() - _startup_time,
        }

    return app


# Create default app instance
app = create_app()
