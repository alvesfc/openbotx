"""Base embedding provider for OpenBotX."""

from abc import abstractmethod
from typing import Any

from openbotx.models.enums import ProviderStatus, ProviderType
from openbotx.providers.base import ProviderBase, ProviderHealth


class EmbeddingProvider(ProviderBase):
    """Base class for embedding providers."""

    provider_type = ProviderType.LLM

    def __init__(self, name: str = "embedding", config: dict[str, Any] | None = None) -> None:
        """Initialize embedding provider.

        Args:
            name: Provider name
            config: Provider configuration
        """
        super().__init__(name, config)
        self._initialized = False

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Return the embedding dimensions."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model name."""
        pass

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Embed a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        pass

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in batch.

        Args:
            texts: Texts to embed

        Returns:
            List of embedding vectors
        """
        pass

    async def initialize(self) -> None:
        """Initialize the provider."""
        self._set_status(ProviderStatus.INITIALIZED)
        self._initialized = True

    async def start(self) -> None:
        """Start the provider."""
        self._set_status(ProviderStatus.RUNNING)

    async def stop(self) -> None:
        """Stop the provider."""
        self._set_status(ProviderStatus.STOPPED)

    async def health_check(self) -> ProviderHealth:
        """Check provider health."""
        return ProviderHealth(
            healthy=self._initialized,
            status=self.status,
            message="Embedding provider ready" if self._initialized else "Not initialized",
            details={
                "model": self.model_name,
                "dimensions": self.dimensions,
            },
        )
