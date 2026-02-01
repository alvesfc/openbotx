"""Memory models for OpenBotX vector memory system."""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MemorySource(str, Enum):
    """Source of memory content."""

    MEMORY = "memory"
    SESSIONS = "sessions"
    EXTRA = "extra"


class Chunk(BaseModel):
    """A chunk of text for embedding and search."""

    id: int | None = None
    path: str
    source: MemorySource
    start_line: int
    end_line: int
    text: str
    hash: str
    embedding: list[float] | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def line_count(self) -> int:
        """Number of lines in this chunk."""
        return self.end_line - self.start_line + 1


class MemoryFile(BaseModel):
    """A file tracked in the memory index."""

    path: str
    hash: str
    mtime: float
    size: int
    source: MemorySource
    indexed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    chunk_count: int = 0


class MemorySearchResult(BaseModel):
    """Result from a memory search."""

    path: str
    source: MemorySource
    start_line: int
    end_line: int
    score: float
    snippet: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    def __str__(self) -> str:
        """String representation of search result."""
        return f"{self.path}:{self.start_line}-{self.end_line} (score: {self.score:.2f})"


class MemoryIndexMeta(BaseModel):
    """Metadata about the memory index."""

    version: str = "1.0.0"
    embedding_model: str = ""
    embedding_dimensions: int = 0
    chunk_size: int = 500
    chunk_overlap: int = 50
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    file_count: int = 0
    chunk_count: int = 0


class MemoryStats(BaseModel):
    """Statistics about the memory index."""

    total_files: int = 0
    total_chunks: int = 0
    total_tokens: int = 0
    sources: dict[str, int] = Field(default_factory=dict)
    last_sync: datetime | None = None
    index_size_bytes: int = 0
