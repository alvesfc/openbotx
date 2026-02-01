"""Gateway manager for OpenBotX - manages async gateway lifecycle."""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from openbotx.helpers.logger import get_logger
from openbotx.models.enums import ProviderStatus
from openbotx.providers.gateway.base import GatewayProvider


class GatewayStatus(str, Enum):
    """Status of a managed gateway."""

    REGISTERED = "registered"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"
    RESTARTING = "restarting"


@dataclass
class GatewayInfo:
    """Information about a managed gateway."""

    name: str
    gateway: GatewayProvider
    status: GatewayStatus = GatewayStatus.REGISTERED
    task: asyncio.Task[None] | None = None
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    error: str | None = None
    restart_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class GatewayManager:
    """
    Manages the lifecycle of all gateway providers.

    Each gateway runs in its own async task without blocking others.
    Provides centralized control for starting, stopping, and monitoring gateways.
    """

    def __init__(self, auto_restart: bool = False, max_restarts: int = 3) -> None:
        """Initialize gateway manager.

        Args:
            auto_restart: Whether to automatically restart failed gateways
            max_restarts: Maximum number of automatic restarts per gateway
        """
        self._gateways: dict[str, GatewayInfo] = {}
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._auto_restart = auto_restart
        self._max_restarts = max_restarts
        self._logger = get_logger("gateway_manager")

    @property
    def is_running(self) -> bool:
        """Check if gateway manager is running."""
        return self._running

    @property
    def gateway_count(self) -> int:
        """Get number of registered gateways."""
        return len(self._gateways)

    def register(self, name: str, gateway: GatewayProvider) -> None:
        """Register a gateway without starting it.

        Args:
            name: Unique name for the gateway
            gateway: Gateway provider instance

        Raises:
            ValueError: If gateway with name already exists
        """
        if name in self._gateways:
            raise ValueError(f"Gateway '{name}' already registered")

        self._gateways[name] = GatewayInfo(name=name, gateway=gateway)
        self._logger.info("gateway_registered", name=name, type=gateway.gateway_type.value)

    def unregister(self, name: str) -> bool:
        """Unregister a gateway.

        Args:
            name: Gateway name to unregister

        Returns:
            True if gateway was unregistered
        """
        if name not in self._gateways:
            return False

        info = self._gateways[name]
        if info.status == GatewayStatus.RUNNING:
            self._logger.warning("unregistering_running_gateway", name=name)

        del self._gateways[name]
        self._logger.info("gateway_unregistered", name=name)
        return True

    def get(self, name: str) -> GatewayProvider | None:
        """Get a gateway by name.

        Args:
            name: Gateway name

        Returns:
            Gateway provider or None if not found
        """
        info = self._gateways.get(name)
        return info.gateway if info else None

    def get_info(self, name: str) -> GatewayInfo | None:
        """Get gateway info by name.

        Args:
            name: Gateway name

        Returns:
            GatewayInfo or None if not found
        """
        return self._gateways.get(name)

    def list_gateways(self) -> list[str]:
        """List all registered gateway names."""
        return list(self._gateways.keys())

    async def start_gateway(self, name: str) -> bool:
        """Start a specific gateway in its own task.

        Args:
            name: Gateway name to start

        Returns:
            True if gateway was started
        """
        info = self._gateways.get(name)
        if not info:
            self._logger.error("gateway_not_found", name=name)
            return False

        if info.status == GatewayStatus.RUNNING:
            self._logger.warning("gateway_already_running", name=name)
            return True

        try:
            info.status = GatewayStatus.STARTING

            # initialize if needed
            if info.gateway.status == ProviderStatus.INITIALIZED:
                await info.gateway.initialize()

            # start gateway
            await info.gateway.start()

            # create task for gateway run loop if it has one
            if hasattr(info.gateway, "_run"):
                info.task = asyncio.create_task(
                    self._run_gateway_wrapper(name),
                    name=f"gateway-{name}",
                )

            info.status = GatewayStatus.RUNNING
            info.started_at = datetime.now(UTC)
            info.error = None

            self._logger.info("gateway_started", name=name)
            return True

        except Exception as e:
            info.status = GatewayStatus.ERROR
            info.error = str(e)
            self._logger.error("gateway_start_error", name=name, error=str(e))
            return False

    async def _run_gateway_wrapper(self, name: str) -> None:
        """Wrapper for running a gateway with error handling.

        Args:
            name: Gateway name
        """
        info = self._gateways.get(name)
        if not info:
            return

        try:
            await info.gateway._run()
        except asyncio.CancelledError:
            self._logger.info("gateway_cancelled", name=name)
        except Exception as e:
            info.status = GatewayStatus.ERROR
            info.error = str(e)
            self._logger.error("gateway_run_error", name=name, error=str(e))

            # auto restart if enabled
            if self._auto_restart and info.restart_count < self._max_restarts:
                info.restart_count += 1
                self._logger.info(
                    "gateway_auto_restart",
                    name=name,
                    attempt=info.restart_count,
                    max=self._max_restarts,
                )
                await asyncio.sleep(1.0)  # brief delay before restart
                await self.start_gateway(name)

    async def stop_gateway(self, name: str, timeout: float = 5.0) -> bool:
        """Stop a specific gateway gracefully.

        Args:
            name: Gateway name to stop
            timeout: Maximum time to wait for graceful shutdown

        Returns:
            True if gateway was stopped
        """
        info = self._gateways.get(name)
        if not info:
            self._logger.error("gateway_not_found", name=name)
            return False

        if info.status not in (GatewayStatus.RUNNING, GatewayStatus.ERROR):
            return True

        try:
            info.status = GatewayStatus.STOPPING

            # stop the gateway
            await info.gateway.stop()

            # cancel task if running
            if info.task and not info.task.done():
                info.task.cancel()
                try:
                    await asyncio.wait_for(info.task, timeout=timeout)
                except TimeoutError:
                    self._logger.warning("gateway_stop_timeout", name=name)
                except asyncio.CancelledError:
                    pass

            info.status = GatewayStatus.STOPPED
            info.stopped_at = datetime.now(UTC)
            info.task = None

            self._logger.info("gateway_stopped", name=name)
            return True

        except Exception as e:
            info.status = GatewayStatus.ERROR
            info.error = str(e)
            self._logger.error("gateway_stop_error", name=name, error=str(e))
            return False

    async def restart_gateway(self, name: str) -> bool:
        """Restart a specific gateway.

        Args:
            name: Gateway name to restart

        Returns:
            True if gateway was restarted
        """
        info = self._gateways.get(name)
        if not info:
            return False

        info.status = GatewayStatus.RESTARTING
        self._logger.info("gateway_restarting", name=name)

        await self.stop_gateway(name)
        return await self.start_gateway(name)

    async def start_all(self) -> dict[str, bool]:
        """Start all registered gateways concurrently.

        Returns:
            Dict mapping gateway names to success status
        """
        self._running = True
        self._shutdown_event.clear()

        results = {}
        tasks = []

        for name in self._gateways:
            tasks.append(self._start_gateway_with_result(name))

        started = await asyncio.gather(*tasks, return_exceptions=True)

        for name, result in zip(self._gateways.keys(), started, strict=False):
            if isinstance(result, Exception):
                results[name] = False
                self._logger.error("gateway_start_failed", name=name, error=str(result))
            else:
                results[name] = result

        running_count = sum(1 for v in results.values() if v)
        self._logger.info("all_gateways_started", total=len(results), running=running_count)

        return results

    async def _start_gateway_with_result(self, name: str) -> bool:
        """Start a gateway and return result.

        Args:
            name: Gateway name

        Returns:
            True if started successfully
        """
        try:
            return await self.start_gateway(name)
        except Exception:
            return False

    async def stop_all(self, timeout: float = 10.0) -> dict[str, bool]:
        """Stop all gateways gracefully.

        Args:
            timeout: Maximum time to wait for all gateways to stop

        Returns:
            Dict mapping gateway names to success status
        """
        self._running = False
        self._shutdown_event.set()

        results = {}
        tasks = []

        for name in self._gateways:
            tasks.append(self._stop_gateway_with_result(name, timeout / 2))

        stopped = await asyncio.gather(*tasks, return_exceptions=True)

        for name, result in zip(self._gateways.keys(), stopped, strict=False):
            if isinstance(result, Exception):
                results[name] = False
            else:
                results[name] = result

        stopped_count = sum(1 for v in results.values() if v)
        self._logger.info("all_gateways_stopped", total=len(results), stopped=stopped_count)

        return results

    async def _stop_gateway_with_result(self, name: str, timeout: float) -> bool:
        """Stop a gateway and return result.

        Args:
            name: Gateway name
            timeout: Stop timeout

        Returns:
            True if stopped successfully
        """
        try:
            return await self.stop_gateway(name, timeout)
        except Exception:
            return False

    def get_status(self) -> dict[str, dict[str, Any]]:
        """Get status of all gateways.

        Returns:
            Dict mapping gateway names to status info
        """
        status = {}
        for name, info in self._gateways.items():
            status[name] = {
                "status": info.status.value,
                "type": info.gateway.gateway_type.value,
                "started_at": info.started_at.isoformat() if info.started_at else None,
                "stopped_at": info.stopped_at.isoformat() if info.stopped_at else None,
                "error": info.error,
                "restart_count": info.restart_count,
            }
        return status

    def get_running_gateways(self) -> list[str]:
        """Get list of currently running gateway names."""
        return [
            name for name, info in self._gateways.items() if info.status == GatewayStatus.RUNNING
        ]

    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown signal."""
        await self._shutdown_event.wait()

    def set_message_handler(self, handler: Any) -> None:
        """Set message handler on all gateways.

        Args:
            handler: Message handler callback
        """
        for info in self._gateways.values():
            info.gateway.set_message_handler(handler)


# global instance
_gateway_manager: GatewayManager | None = None


def get_gateway_manager() -> GatewayManager:
    """Get the global gateway manager instance."""
    global _gateway_manager
    if _gateway_manager is None:
        _gateway_manager = GatewayManager()
    return _gateway_manager


def set_gateway_manager(manager: GatewayManager) -> None:
    """Set the global gateway manager instance."""
    global _gateway_manager
    _gateway_manager = manager
