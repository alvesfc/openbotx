"""Local embedding provider using sentence-transformers."""

from typing import Any

from openbotx.providers.embedding.base import EmbeddingProvider


class LocalEmbeddingProvider(EmbeddingProvider):
    """Local embeddings using sentence-transformers.

    Default model: all-MiniLM-L6-v2 (384 dimensions, fast, good quality)
    """

    def __init__(self, name: str = "local-embedding", config: dict[str, Any] | None = None) -> None:
        """Initialize local embedding provider.

        Args:
            name: Provider name
            config: Configuration with optional model name
        """
        super().__init__(name, config)
        config = config or {}

        self._model_name = config.get("model", "all-MiniLM-L6-v2")
        self._model = None
        self._dims = 0

    @property
    def dimensions(self) -> int:
        """Return the embedding dimensions."""
        return self._dims

    @property
    def model_name(self) -> str:
        """Return the model name."""
        return self._model_name

    async def initialize(self) -> None:
        """Initialize the sentence-transformers model."""
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
            self._dims = self._model.get_sentence_embedding_dimension()

            await super().initialize()
            self._logger.info(
                "local_embedding_initialized",
                model=self._model_name,
                dimensions=self._dims,
            )

        except ImportError:
            raise RuntimeError(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )

    async def embed(self, text: str) -> list[float]:
        """Embed a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        if not self._model:
            raise RuntimeError("Provider not initialized")

        embedding = self._model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in batch.

        Args:
            texts: Texts to embed

        Returns:
            List of embedding vectors
        """
        if not self._model:
            raise RuntimeError("Provider not initialized")

        if not texts:
            return []

        embeddings = self._model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return [e.tolist() for e in embeddings]

    async def stop(self) -> None:
        """Stop the provider."""
        self._model = None
        await super().stop()
