"""OpenAI embedding provider for OpenBotX."""

import os
from typing import Any

from openai import AsyncOpenAI

from openbotx.providers.embedding.base import EmbeddingProvider


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI embeddings using text-embedding-3-small."""

    def __init__(
        self, name: str = "openai-embedding", config: dict[str, Any] | None = None
    ) -> None:
        """Initialize OpenAI embedding provider.

        Args:
            name: Provider name
            config: Configuration with optional api_key, model, dimensions
        """
        super().__init__(name, config)
        config = config or {}

        self._api_key = config.get("api_key") or os.getenv("OPENAI_API_KEY")
        self._model = config.get("model", "text-embedding-3-small")
        self._dimensions_config = config.get("dimensions", 1536)
        self._client: AsyncOpenAI | None = None

    @property
    def dimensions(self) -> int:
        """Return the embedding dimensions."""
        return self._dimensions_config

    @property
    def model_name(self) -> str:
        """Return the model name."""
        return self._model

    async def initialize(self) -> None:
        """Initialize the OpenAI client."""
        if not self._api_key:
            raise ValueError("OpenAI API key not configured")

        self._client = AsyncOpenAI(api_key=self._api_key)
        await super().initialize()
        self._logger.info("openai_embedding_initialized", model=self._model)

    async def embed(self, text: str) -> list[float]:
        """Embed a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        if not self._client:
            raise RuntimeError("Provider not initialized")

        # truncate if too long
        text = text[:8000] if len(text) > 8000 else text

        response = await self._client.embeddings.create(
            model=self._model,
            input=text,
            dimensions=self._dimensions_config,
        )

        return response.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in batch.

        Args:
            texts: Texts to embed

        Returns:
            List of embedding vectors
        """
        if not self._client:
            raise RuntimeError("Provider not initialized")

        if not texts:
            return []

        # truncate each text if too long
        texts = [t[:8000] if len(t) > 8000 else t for t in texts]

        # openai supports batching up to certain limit
        batch_size = 100
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]

            response = await self._client.embeddings.create(
                model=self._model,
                input=batch,
                dimensions=self._dimensions_config,
            )

            # sort by index to maintain order
            sorted_data = sorted(response.data, key=lambda x: x.index)
            all_embeddings.extend([d.embedding for d in sorted_data])

        return all_embeddings

    async def stop(self) -> None:
        """Stop the provider."""
        if self._client:
            await self._client.close()
            self._client = None
        await super().stop()
