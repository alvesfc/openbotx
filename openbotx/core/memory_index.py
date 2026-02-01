"""Memory index for OpenBotX - vector-based memory with hybrid search."""

import hashlib
import os
import sqlite3
import struct
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openbotx.helpers.logger import get_logger
from openbotx.helpers.tokens import count_tokens
from openbotx.models.memory import (
    Chunk,
    MemorySearchResult,
    MemorySource,
    MemoryStats,
)
from openbotx.providers.embedding.base import EmbeddingProvider


def _serialize_embedding(embedding: list[float]) -> bytes:
    """Serialize embedding to bytes for sqlite-vec."""
    return struct.pack(f"{len(embedding)}f", *embedding)


def _deserialize_embedding(data: bytes, dimensions: int) -> list[float]:
    """Deserialize embedding from bytes."""
    return list(struct.unpack(f"{dimensions}f", data))


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    if len(a) != len(b) or len(a) == 0:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class MemoryIndex:
    """
    Vector-based memory system using SQLite + sqlite-vec.

    Provides hybrid search combining vector similarity and text search.
    """

    def __init__(
        self,
        db_path: str,
        embedding_provider: EmbeddingProvider,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> None:
        """Initialize memory index.

        Args:
            db_path: Path to SQLite database file
            embedding_provider: Provider for generating embeddings
            chunk_size: Target chunk size in tokens
            chunk_overlap: Overlap between chunks in tokens
        """
        self._db_path = db_path
        self._embedding_provider = embedding_provider
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._conn: sqlite3.Connection | None = None
        self._logger = get_logger("memory_index")
        self._initialized = False
        self._use_vec = False

    @property
    def is_initialized(self) -> bool:
        """Check if index is initialized."""
        return self._initialized

    async def initialize(self) -> None:
        """Initialize database with tables and indexes."""
        # ensure directory exists
        db_dir = os.path.dirname(self._db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        # try to load sqlite-vec extension
        try:
            self._conn.enable_load_extension(True)
            # try common paths for sqlite-vec
            vec_paths = [
                "vec0",
                "/usr/local/lib/vec0",
                "/opt/homebrew/lib/vec0",
            ]
            for vec_path in vec_paths:
                try:
                    self._conn.load_extension(vec_path)
                    self._use_vec = True
                    self._logger.info("sqlite_vec_loaded", path=vec_path)
                    break
                except Exception:
                    continue

            if not self._use_vec:
                self._logger.warning("sqlite_vec_not_available")
        except Exception as e:
            self._logger.warning("sqlite_extensions_disabled", error=str(e))

        self._create_schema()
        self._initialized = True
        self._logger.info("memory_index_initialized", db_path=self._db_path, use_vec=self._use_vec)

    def _create_schema(self) -> None:
        """Create database schema."""
        cursor = self._conn.cursor()

        # metadata table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """
        )

        # files tracking table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                hash TEXT NOT NULL,
                mtime REAL NOT NULL,
                size INTEGER NOT NULL,
                source TEXT NOT NULL,
                indexed_at TEXT NOT NULL
            )
        """
        )

        # text chunks table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                source TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                hash TEXT NOT NULL,
                text TEXT NOT NULL,
                embedding BLOB,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (path) REFERENCES files(path) ON DELETE CASCADE
            )
        """
        )

        # create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_hash ON chunks(hash)")

        # create FTS5 virtual table for text search
        cursor.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                text,
                content=chunks,
                content_rowid=id
            )
        """
        )

        # create triggers to keep FTS in sync
        cursor.execute(
            """
            CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
                INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
            END
        """
        )

        cursor.execute(
            """
            CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
                INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', old.id, old.text);
            END
        """
        )

        cursor.execute(
            """
            CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
                INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', old.id, old.text);
                INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
            END
        """
        )

        # create vector table if sqlite-vec is available
        if self._use_vec:
            dims = self._embedding_provider.dimensions
            try:
                cursor.execute(
                    f"""
                    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(
                        chunk_id INTEGER PRIMARY KEY,
                        embedding FLOAT[{dims}]
                    )
                """
                )
            except Exception as e:
                self._logger.warning("vec_table_creation_failed", error=str(e))
                self._use_vec = False

        self._conn.commit()

    async def index_file(self, path: str, source: MemorySource = MemorySource.MEMORY) -> int:
        """Index a file's contents into the memory system.

        Args:
            path: Path to the file
            source: Source category of the file

        Returns:
            Number of chunks created
        """
        file_path = Path(path)
        if not file_path.exists():
            self._logger.warning("file_not_found", path=path)
            return 0

        # read file
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            self._logger.error("file_read_error", path=path, error=str(e))
            return 0

        # calculate hash
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

        # check if already indexed with same hash
        cursor = self._conn.cursor()
        cursor.execute("SELECT hash FROM files WHERE path = ?", (path,))
        row = cursor.fetchone()
        if row and row["hash"] == content_hash:
            self._logger.debug("file_already_indexed", path=path)
            return 0

        # remove old chunks for this file
        cursor.execute("DELETE FROM chunks WHERE path = ?", (path,))
        if self._use_vec:
            cursor.execute(
                "DELETE FROM chunks_vec WHERE chunk_id IN (SELECT id FROM chunks WHERE path = ?)",
                (path,),
            )

        # chunk the content
        chunks = self._chunk_text(content, path, source)
        if not chunks:
            return 0

        # generate embeddings in batch
        texts = [c.text for c in chunks]
        try:
            embeddings = await self._embedding_provider.embed_batch(texts)
        except Exception as e:
            self._logger.error("embedding_error", path=path, error=str(e))
            return 0

        # insert chunks
        now = datetime.now(UTC).isoformat()
        for chunk, embedding in zip(chunks, embeddings, strict=False):
            chunk.embedding = embedding
            cursor.execute(
                """
                INSERT INTO chunks (path, source, start_line, end_line, hash, text, embedding, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.path,
                    chunk.source.value,
                    chunk.start_line,
                    chunk.end_line,
                    chunk.hash,
                    chunk.text,
                    _serialize_embedding(embedding),
                    now,
                ),
            )
            chunk_id = cursor.lastrowid

            # insert into vector table
            if self._use_vec and chunk_id:
                try:
                    cursor.execute(
                        "INSERT INTO chunks_vec (chunk_id, embedding) VALUES (?, ?)",
                        (chunk_id, _serialize_embedding(embedding)),
                    )
                except Exception as e:
                    self._logger.warning("vec_insert_error", chunk_id=chunk_id, error=str(e))

        # update file record
        stat = file_path.stat()
        cursor.execute(
            """
            INSERT OR REPLACE INTO files (path, hash, mtime, size, source, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (path, content_hash, stat.st_mtime, stat.st_size, source.value, now),
        )

        self._conn.commit()
        self._logger.info("file_indexed", path=path, chunks=len(chunks))
        return len(chunks)

    async def index_text(
        self,
        text: str,
        path: str,
        source: MemorySource = MemorySource.MEMORY,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Index arbitrary text content.

        Args:
            text: Text content to index
            path: Virtual path for the content
            source: Source category
            metadata: Optional metadata

        Returns:
            Number of chunks created
        """
        content_hash = hashlib.sha256(text.encode()).hexdigest()[:16]

        cursor = self._conn.cursor()

        # remove old chunks
        cursor.execute("DELETE FROM chunks WHERE path = ?", (path,))

        # chunk the content
        chunks = self._chunk_text(text, path, source)
        if not chunks:
            return 0

        # generate embeddings
        texts = [c.text for c in chunks]
        try:
            embeddings = await self._embedding_provider.embed_batch(texts)
        except Exception as e:
            self._logger.error("embedding_error", path=path, error=str(e))
            return 0

        # insert chunks
        now = datetime.now(UTC).isoformat()
        for chunk, embedding in zip(chunks, embeddings, strict=False):
            cursor.execute(
                """
                INSERT INTO chunks (path, source, start_line, end_line, hash, text, embedding, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.path,
                    chunk.source.value,
                    chunk.start_line,
                    chunk.end_line,
                    chunk.hash,
                    chunk.text,
                    _serialize_embedding(embedding),
                    now,
                ),
            )

        # update file record
        cursor.execute(
            """
            INSERT OR REPLACE INTO files (path, hash, mtime, size, source, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (path, content_hash, 0.0, len(text), source.value, now),
        )

        self._conn.commit()
        return len(chunks)

    def _chunk_text(self, text: str, path: str, source: MemorySource) -> list[Chunk]:
        """Split text into overlapping chunks.

        Args:
            text: Text to chunk
            path: File path
            source: Memory source

        Returns:
            List of chunks
        """
        lines = text.split("\n")
        chunks = []

        current_chunk_lines = []
        current_chunk_tokens = 0
        start_line = 1

        for i, line in enumerate(lines, 1):
            line_tokens = count_tokens(line)

            # if adding this line exceeds chunk size, save current chunk
            if current_chunk_tokens + line_tokens > self._chunk_size and current_chunk_lines:
                chunk_text = "\n".join(current_chunk_lines)
                chunk_hash = hashlib.sha256(chunk_text.encode()).hexdigest()[:16]

                chunks.append(
                    Chunk(
                        path=path,
                        source=source,
                        start_line=start_line,
                        end_line=i - 1,
                        text=chunk_text,
                        hash=chunk_hash,
                    )
                )

                # keep overlap lines
                overlap_tokens = 0
                overlap_lines = []
                for line in reversed(current_chunk_lines):
                    lt = count_tokens(line)
                    if overlap_tokens + lt > self._chunk_overlap:
                        break
                    overlap_lines.insert(0, line)
                    overlap_tokens += lt

                current_chunk_lines = overlap_lines
                current_chunk_tokens = overlap_tokens
                start_line = i - len(overlap_lines)

            current_chunk_lines.append(line)
            current_chunk_tokens += line_tokens

        # save remaining chunk
        if current_chunk_lines:
            chunk_text = "\n".join(current_chunk_lines)
            chunk_hash = hashlib.sha256(chunk_text.encode()).hexdigest()[:16]

            chunks.append(
                Chunk(
                    path=path,
                    source=source,
                    start_line=start_line,
                    end_line=len(lines),
                    text=chunk_text,
                    hash=chunk_hash,
                )
            )

        return chunks

    async def search(
        self,
        query: str,
        max_results: int = 10,
        min_score: float = 0.3,
        sources: list[MemorySource] | None = None,
        vector_weight: float = 0.7,
        text_weight: float = 0.3,
    ) -> list[MemorySearchResult]:
        """Hybrid search combining vector and text search.

        Args:
            query: Search query
            max_results: Maximum number of results
            min_score: Minimum score threshold (0-1)
            sources: Filter by sources
            vector_weight: Weight for vector search (0-1)
            text_weight: Weight for text search (0-1)

        Returns:
            List of search results
        """
        if not self._initialized:
            return []

        results_map: dict[int, dict[str, Any]] = {}

        # vector search (sqlite-vec when available, else in-memory over chunks)
        try:
            query_embedding = await self._embedding_provider.embed(query)
            if self._use_vec:
                vec_results = self._vector_search(query_embedding, max_results * 2, sources)
            else:
                vec_results = self._vector_search_in_memory(
                    query_embedding, max_results * 2, sources
                )
            for chunk_id, score in vec_results:
                if chunk_id not in results_map:
                    results_map[chunk_id] = {"vec_score": 0, "text_score": 0}
                results_map[chunk_id]["vec_score"] = score
        except Exception as e:
            self._logger.warning("vector_search_error", error=str(e))

        # text search
        text_results = self._text_search(query, max_results * 2, sources)
        for chunk_id, score in text_results:
            if chunk_id not in results_map:
                results_map[chunk_id] = {"vec_score": 0, "text_score": 0}
            results_map[chunk_id]["text_score"] = score

        # combine scores
        combined = []
        for chunk_id, scores in results_map.items():
            combined_score = (
                scores["vec_score"] * vector_weight + scores["text_score"] * text_weight
            )
            if combined_score >= min_score:
                combined.append((chunk_id, combined_score))

        # sort by score
        combined.sort(key=lambda x: x[1], reverse=True)

        # fetch chunk details
        results = []
        cursor = self._conn.cursor()
        for chunk_id, score in combined[:max_results]:
            cursor.execute(
                "SELECT path, source, start_line, end_line, text FROM chunks WHERE id = ?",
                (chunk_id,),
            )
            row = cursor.fetchone()
            if row:
                snippet = self._generate_snippet(row["text"], query)
                results.append(
                    MemorySearchResult(
                        path=row["path"],
                        source=MemorySource(row["source"]),
                        start_line=row["start_line"],
                        end_line=row["end_line"],
                        score=score,
                        snippet=snippet,
                    )
                )

        return results

    def _vector_search_in_memory(
        self,
        query_embedding: list[float],
        limit: int,
        sources: list[MemorySource] | None,
    ) -> list[tuple[int, float]]:
        """Vector similarity search over chunks when sqlite-vec is not available."""
        cursor = self._conn.cursor()
        dims = len(query_embedding)
        if dims == 0:
            return []

        if sources:
            source_values = [s.value for s in sources]
            placeholders = ",".join(["?" for _ in source_values])
            cursor.execute(
                f"""
                SELECT id, embedding FROM chunks
                WHERE embedding IS NOT NULL AND LENGTH(embedding) = ? AND source IN ({placeholders})
                """,
                (dims * 4, *source_values),
            )
        else:
            cursor.execute(
                """
                SELECT id, embedding FROM chunks
                WHERE embedding IS NOT NULL AND LENGTH(embedding) = ?
                """,
                (dims * 4,),
            )

        scored = []
        for row in cursor.fetchall():
            try:
                emb = _deserialize_embedding(row["embedding"], dims)
                score = _cosine_similarity(query_embedding, emb)
                if not (0 <= score <= 1):
                    score = max(0, min(1, score))
                scored.append((row["id"], score))
            except (struct.error, TypeError):
                continue

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    def _vector_search(
        self,
        query_embedding: list[float],
        limit: int,
        sources: list[MemorySource] | None,
    ) -> list[tuple[int, float]]:
        """Perform vector similarity search via sqlite-vec (ANN).

        Args:
            query_embedding: Query embedding vector
            limit: Maximum results
            sources: Filter by sources

        Returns:
            List of (chunk_id, score) tuples
        """
        cursor = self._conn.cursor()

        # use sqlite-vec for ANN search
        query_blob = _serialize_embedding(query_embedding)

        if sources:
            source_values = [s.value for s in sources]
            placeholders = ",".join(["?" for _ in source_values])
            cursor.execute(
                f"""
                SELECT v.chunk_id, v.distance
                FROM chunks_vec v
                JOIN chunks c ON c.id = v.chunk_id
                WHERE c.source IN ({placeholders})
                ORDER BY v.embedding <-> ?
                LIMIT ?
                """,
                (*source_values, query_blob, limit),
            )
        else:
            cursor.execute(
                """
                SELECT chunk_id, distance
                FROM chunks_vec
                ORDER BY embedding <-> ?
                LIMIT ?
                """,
                (query_blob, limit),
            )

        results = []
        for row in cursor.fetchall():
            # convert distance to similarity score (1 - normalized_distance)
            distance = row["distance"] if isinstance(row["distance"], float) else 0
            score = max(0, 1 - (distance / 2))  # normalize assuming max distance ~2
            results.append((row["chunk_id"], score))

        return results

    def _text_search(
        self,
        query: str,
        limit: int,
        sources: list[MemorySource] | None,
    ) -> list[tuple[int, float]]:
        """Perform full-text search using FTS5.

        Args:
            query: Search query
            limit: Maximum results
            sources: Filter by sources

        Returns:
            List of (chunk_id, score) tuples
        """
        cursor = self._conn.cursor()

        # prepare FTS5 query
        fts_query = " OR ".join(query.split())

        try:
            if sources:
                source_values = [s.value for s in sources]
                placeholders = ",".join(["?" for _ in source_values])
                cursor.execute(
                    f"""
                    SELECT c.id, bm25(chunks_fts) as score
                    FROM chunks_fts f
                    JOIN chunks c ON c.id = f.rowid
                    WHERE chunks_fts MATCH ? AND c.source IN ({placeholders})
                    ORDER BY score
                    LIMIT ?
                    """,
                    (fts_query, *source_values, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT c.id, bm25(chunks_fts) as score
                    FROM chunks_fts f
                    JOIN chunks c ON c.id = f.rowid
                    WHERE chunks_fts MATCH ?
                    ORDER BY score
                    LIMIT ?
                    """,
                    (fts_query, limit),
                )

            results = []
            for row in cursor.fetchall():
                # bm25 returns negative scores, convert to positive
                score = min(1.0, abs(row["score"]) / 10)
                results.append((row["id"], score))

            return results

        except Exception as e:
            self._logger.warning("text_search_error", error=str(e))
            return []

    def _generate_snippet(self, text: str, query: str, max_length: int = 500) -> str:
        """Generate a snippet from text highlighting query terms.

        Args:
            text: Full text
            query: Search query
            max_length: Maximum snippet length

        Returns:
            Snippet string
        """
        if len(text) <= max_length:
            return text

        # find best starting position based on query terms
        query_terms = query.lower().split()
        text_lower = text.lower()

        best_pos = 0
        best_count = 0

        for i in range(0, len(text) - max_length, 50):
            window = text_lower[i : i + max_length]
            count = sum(1 for term in query_terms if term in window)
            if count > best_count:
                best_count = count
                best_pos = i

        # extract snippet
        snippet = text[best_pos : best_pos + max_length]

        # add ellipsis if truncated
        if best_pos > 0:
            snippet = "..." + snippet[3:]
        if best_pos + max_length < len(text):
            snippet = snippet[:-3] + "..."

        return snippet

    async def get(self, path: str) -> str | None:
        """Get full content of a memory file.

        Args:
            path: File path

        Returns:
            File content or None if not found
        """
        file_path = Path(path)
        if file_path.exists():
            try:
                return file_path.read_text(encoding="utf-8")
            except Exception:
                pass

        # try to reconstruct from chunks
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT text FROM chunks WHERE path = ? ORDER BY start_line",
            (path,),
        )
        rows = cursor.fetchall()
        if rows:
            return "\n".join(row["text"] for row in rows)

        return None

    async def sync(self, paths: list[str], source: MemorySource = MemorySource.MEMORY) -> int:
        """Sync memory files with the index.

        Args:
            paths: List of file paths or directories to sync
            source: Source category for these files

        Returns:
            Number of files synced
        """
        synced = 0

        for path in paths:
            p = Path(path)
            if p.is_file():
                chunks = await self.index_file(str(p), source)
                if chunks > 0:
                    synced += 1
            elif p.is_dir():
                for file_path in p.rglob("*.md"):
                    chunks = await self.index_file(str(file_path), source)
                    if chunks > 0:
                        synced += 1

        return synced

    def get_stats(self) -> MemoryStats:
        """Get statistics about the memory index.

        Returns:
            MemoryStats object
        """
        cursor = self._conn.cursor()

        # count files by source
        cursor.execute("SELECT source, COUNT(*) as count FROM files GROUP BY source")
        sources = {row["source"]: row["count"] for row in cursor.fetchall()}

        # total counts
        cursor.execute("SELECT COUNT(*) as count FROM files")
        total_files = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) as count FROM chunks")
        total_chunks = cursor.fetchone()["count"]

        # get last sync time
        cursor.execute("SELECT MAX(indexed_at) as last FROM files")
        row = cursor.fetchone()
        last_sync = datetime.fromisoformat(row["last"]) if row["last"] else None

        # get index size
        try:
            index_size = os.path.getsize(self._db_path)
        except Exception:
            index_size = 0

        return MemoryStats(
            total_files=total_files,
            total_chunks=total_chunks,
            sources=sources,
            last_sync=last_sync,
            index_size_bytes=index_size,
        )

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            self._initialized = False


# global instance
_memory_index: MemoryIndex | None = None


def get_memory_index() -> MemoryIndex | None:
    """Get the global memory index instance."""
    return _memory_index


def set_memory_index(index: MemoryIndex) -> None:
    """Set the global memory index instance."""
    global _memory_index
    _memory_index = index
