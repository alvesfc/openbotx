"""Memory index initialization helper for OpenBotX."""

import os

from openbotx.core.memory_index import MemoryIndex, set_memory_index
from openbotx.helpers.config import Config
from openbotx.helpers.logger import get_logger
from openbotx.providers.embedding.local import LocalEmbeddingProvider

_logger = get_logger("memory_loader")


async def initialize_memory_index(config: Config) -> MemoryIndex | None:
    """Initialize the memory index with local embeddings (sentence-transformers + tiktoken).

    Memory is always enabled. Config only sets paths, model, and chunk sizes.

    Args:
        config: Application configuration

    Returns:
        MemoryIndex instance or None on init failure
    """
    memory_db_path = os.getenv("OPENBOTX_MEMORY_DB_PATH", "data/memory.db")
    memory_paths_raw = os.getenv("OPENBOTX_MEMORY_PATHS", "")
    memory_paths = [p.strip() for p in memory_paths_raw.split(",") if p.strip()]

    try:
        embedding_provider = LocalEmbeddingProvider(
            config={
                "model": os.getenv("OPENBOTX_EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
            }
        )
        await embedding_provider.initialize()

        memory_index = MemoryIndex(
            db_path=memory_db_path,
            embedding_provider=embedding_provider,
            chunk_size=int(os.getenv("OPENBOTX_CHUNK_SIZE", "500")),
            chunk_overlap=int(os.getenv("OPENBOTX_CHUNK_OVERLAP", "50")),
        )
        await memory_index.initialize()

        if memory_paths:
            synced = await memory_index.sync(memory_paths)
            _logger.info("memory_synced", files=synced)

        set_memory_index(memory_index)
        _logger.info("memory_index_initialized", db_path=memory_db_path)
        return memory_index

    except Exception as e:
        _logger.error("memory_index_init_failed", error=str(e))
        return None
