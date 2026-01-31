"""System API routes for OpenBotX."""

import platform
import sys
import time

from fastapi import APIRouter

from openbotx.api.schemas import SystemHealthResponse, SystemVersionResponse
from openbotx.core.orchestrator import get_orchestrator
from openbotx.helpers.config import get_config
from openbotx.providers.base import get_provider_registry
from openbotx.version import __version__

router = APIRouter()

# Store startup time
_startup_time = time.time()


@router.get("/health", response_model=SystemHealthResponse)
async def system_health() -> SystemHealthResponse:
    """Get system health status.

    Returns:
        System health
    """
    orchestrator = get_orchestrator()
    registry = get_provider_registry()

    # Check provider health
    health_status = await registry.health_check_all()
    providers = {key: health.healthy for key, health in health_status.items()}

    return SystemHealthResponse(
        status="healthy" if orchestrator.is_running else "unhealthy",
        version=__version__,
        uptime_seconds=time.time() - _startup_time,
        providers=providers,
        stats=orchestrator.stats,
    )


@router.get("/version", response_model=SystemVersionResponse)
async def system_version() -> SystemVersionResponse:
    """Get system version.

    Returns:
        Version info
    """
    config = get_config()

    return SystemVersionResponse(
        version=__version__,
        python_version=sys.version,
        config_version=config.version,
    )


@router.post("/restart")
async def restart_system() -> dict:
    """Request system restart.

    Returns:
        Status message

    Note:
        This signals a restart request but doesn't actually restart.
        The process manager should handle the actual restart.
    """
    # TODO: Implement restart signaling
    return {
        "status": "restart_requested",
        "message": "Restart signal sent. The process manager should handle restart.",
    }


@router.get("/config")
async def get_system_config() -> dict:
    """Get system configuration (non-sensitive parts).

    Returns:
        Configuration summary
    """
    config = get_config()

    return {
        "version": config.version,
        "bot": {
            "name": config.bot.name,
            "description": config.bot.description,
        },
        "database": {
            "type": config.database.type.value,
            "path": config.database.path,
        },
        "storage": {
            "type": config.storage.type.value,
        },
        "llm": {
            "provider": config.llm.provider.value,
            "model": config.llm.model,
        },
        "gateways": {
            "cli": {"enabled": config.gateways.cli.enabled},
            "websocket": {
                "enabled": config.gateways.websocket.enabled,
                "port": config.gateways.websocket.port,
            },
            "telegram": {"enabled": config.gateways.telegram.enabled},
        },
        "api": {
            "host": config.api.host,
            "port": config.api.port,
        },
        "logging": {
            "level": config.logging.level.value,
            "format": config.logging.format.value,
        },
    }


@router.get("/info")
async def system_info() -> dict:
    """Get system information.

    Returns:
        System info
    """
    return {
        "name": "OpenBotX",
        "version": __version__,
        "python": {
            "version": sys.version,
            "implementation": platform.python_implementation(),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "uptime_seconds": time.time() - _startup_time,
    }
