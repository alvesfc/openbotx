"""Background services loader for OpenBotX.

Services that run when the application starts and stop when it shuts down.
Start/stop follow the same pattern as gateways and providers.
"""

import asyncio
from collections.abc import Callable
from typing import Any

from openbotx.helpers.config import Config, get_config
from openbotx.helpers.logger import get_logger

_logger = get_logger("background_loader")

# (name, task) for each running service
_running: list[tuple[str, asyncio.Task[Any]]] = []


def _service_relay(config: Config) -> Any:
    """Relay service: returns coroutine that runs until cancelled."""
    from openbotx.relay.server import run_relay_server

    return run_relay_server(host=config.relay.host, port=config.relay.port)


# name, enabled(config), start_fn(config) -> coroutine that runs until cancelled
_SERVICES: list[tuple[str, Callable[[Config], bool], Callable[[Config], Any]]] = [
    ("relay", lambda c: c.relay.enabled, _service_relay),
]


async def start_background_services(config: Config | None = None) -> list[str]:
    """Start all enabled background services (non-blocking).

    Args:
        config: Configuration (loads from default if not provided).

    Returns:
        List of started service names.
    """
    if config is None:
        config = get_config()
    started: list[str] = []
    for name, enabled, start_fn in _SERVICES:
        if not enabled(config):
            continue
        try:
            coro = start_fn(config)
            task = asyncio.create_task(coro)
            _running.append((name, task))
            started.append(name)
            _logger.info("background_service_started", service=name)
        except Exception as e:
            _logger.error("background_service_start_error", service=name, error=str(e))
    return started


async def stop_background_services() -> None:
    """Stop all running background services (same pattern as stop_all_gateways)."""
    global _running
    for name, task in _running:
        try:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            _logger.info("background_service_stopped", service=name)
        except Exception as e:
            _logger.error("background_service_stop_error", service=name, error=str(e))
    _running = []
