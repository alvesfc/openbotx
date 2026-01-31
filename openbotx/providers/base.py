"""Base provider classes for OpenBotX."""

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from openbotx.helpers.logger import get_logger
from openbotx.models.enums import ProviderStatus, ProviderType


class ProviderHealth(BaseModel):
    """Health status of a provider."""

    healthy: bool = True
    status: ProviderStatus = ProviderStatus.INITIALIZED
    message: str = ""
    last_check: datetime = Field(default_factory=lambda: datetime.now(UTC))
    details: dict[str, Any] = Field(default_factory=dict)


class ProviderBase(ABC):
    """Base class for all providers."""

    provider_type: ProviderType
    name: str

    def __init__(self, name: str, config: dict[str, Any] | None = None) -> None:
        """Initialize provider.

        Args:
            name: Provider name
            config: Provider configuration
        """
        self.name = name
        self.config = config or {}
        self._status = ProviderStatus.INITIALIZED
        self._logger = get_logger(f"provider.{self.provider_type.value}.{name}")

    @property
    def status(self) -> ProviderStatus:
        """Get provider status."""
        return self._status

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the provider.

        Called once when the provider is created.
        """
        pass

    @abstractmethod
    async def start(self) -> None:
        """Start the provider.

        Called when the system starts up.
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the provider.

        Called when the system shuts down.
        """
        pass

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """Check provider health.

        Returns:
            ProviderHealth status
        """
        pass

    def _set_status(self, status: ProviderStatus) -> None:
        """Set provider status.

        Args:
            status: New status
        """
        self._status = status
        self._logger.info("provider_status_changed", status=status.value)

    async def __aenter__(self) -> "ProviderBase":
        """Async context manager entry."""
        await self.initialize()
        await self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.stop()


class ProviderRegistry:
    """Registry for managing providers."""

    def __init__(self) -> None:
        """Initialize provider registry."""
        self._providers: dict[str, ProviderBase] = {}
        self._by_type: dict[ProviderType, list[str]] = {}
        self._logger = get_logger("provider_registry")

    def register(self, provider: ProviderBase) -> None:
        """Register a provider.

        Args:
            provider: Provider to register
        """
        key = f"{provider.provider_type.value}:{provider.name}"
        self._providers[key] = provider

        if provider.provider_type not in self._by_type:
            self._by_type[provider.provider_type] = []
        self._by_type[provider.provider_type].append(key)

        self._logger.info(
            "provider_registered",
            provider_type=provider.provider_type.value,
            name=provider.name,
        )

    def get(
        self,
        provider_type: ProviderType,
        name: str | None = None,
    ) -> ProviderBase | None:
        """Get a provider by type and name.

        Args:
            provider_type: Provider type
            name: Provider name (optional, returns first of type if not specified)

        Returns:
            Provider or None if not found
        """
        if name:
            key = f"{provider_type.value}:{name}"
            return self._providers.get(key)

        # Return first provider of type
        keys = self._by_type.get(provider_type, [])
        if keys:
            return self._providers.get(keys[0])
        return None

    def get_all(self, provider_type: ProviderType | None = None) -> list[ProviderBase]:
        """Get all providers, optionally filtered by type.

        Args:
            provider_type: Provider type to filter by (optional)

        Returns:
            List of providers
        """
        if provider_type is None:
            return list(self._providers.values())

        keys = self._by_type.get(provider_type, [])
        return [self._providers[k] for k in keys if k in self._providers]

    def unregister(self, provider_type: ProviderType, name: str) -> bool:
        """Unregister a provider.

        Args:
            provider_type: Provider type
            name: Provider name

        Returns:
            True if provider was unregistered
        """
        key = f"{provider_type.value}:{name}"
        if key in self._providers:
            del self._providers[key]
            self._by_type[provider_type].remove(key)
            self._logger.info(
                "provider_unregistered",
                provider_type=provider_type.value,
                name=name,
            )
            return True
        return False

    async def start_all(self) -> None:
        """Start all registered providers."""
        for provider in self._providers.values():
            await provider.start()

    async def stop_all(self) -> None:
        """Stop all registered providers."""
        for provider in self._providers.values():
            await provider.stop()

    async def health_check_all(self) -> dict[str, ProviderHealth]:
        """Check health of all providers.

        Returns:
            Dict of provider key to health status
        """
        results = {}
        for key, provider in self._providers.items():
            results[key] = await provider.health_check()
        return results


# Global provider registry
_registry: ProviderRegistry | None = None


def get_provider_registry() -> ProviderRegistry:
    """Get the global provider registry."""
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry
