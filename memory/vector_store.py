"""Persistent local vector indexing for Jarvis long-term memory.

The default embedder is deterministic and offline: it uses signed feature hashing
rather than sending memory contents to a remote embedding service. The SQLite
index is intentionally small, inspectable, and easy to migrate or delete.
"""

from __future__ import annotations

import hashlib
import math
import re
import sqlite3
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol


class EmbeddingProvider(Protocol):
    dimension: int

    def embed(self, text: str) -> tuple[float, ...]:
        ...


class HashEmbedding:
    """Offline signed feature-hash embedding with normalized vectors."""

    def __init__(self, dimension: int = 256) -> None:
        if dimension < 32 or dimension > 4_096:
            raise ValueError("Embedding dimension must be between 32 and 4,096")
        self.dimension = dimension

    def embed(self, text: str) -> tuple[float, ...]:
        tokens = re.findall(r"[a-z0-9_]{2,}", text.lower())
        vector = [0.0] * self.dimension
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:8], "big") % self.dimension
            sign = 1.0 if digest[8] & 1 else -1.0
            weight = 1.0 + min(len(token), 24) / 24.0
            vector[index] += sign * weight
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return tuple(vector)
        return tuple(value / norm for value in vector)


@dataclass(frozen=True)
class VectorMatch:
    memory_id: int
    score: float


class SQLiteVectorStore:
    def __init__(self, path: Path, embedder: EmbeddingProvider | None = None, max_vectors: int = 100_000) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder or HashEmbedding()
        if max_vectors <= 0 or max_vectors > 1_000_000:
            raise ValueError("Vector count limit must be between 1 and 1,000,000")
        self.max_vectors = max_vectors
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS memory_vectors ("
                "memory_id INTEGER PRIMARY KEY, dimension INTEGER NOT NULL, vector BLOB NOT NULL, updated_at TEXT NOT NULL)"
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_memory_vectors_updated ON memory_vectors(updated_at)")

    def upsert(self, memory_id: int, text: str) -> None:
        vector = self.embedder.embed(text)
        packed = struct.pack(f"!{len(vector)}f", *vector)
        with self._connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM memory_vectors").fetchone()[0]
            exists = connection.execute("SELECT 1 FROM memory_vectors WHERE memory_id=?", (int(memory_id),)).fetchone()
            if not exists and int(count) >= self.max_vectors:
                raise ValueError("Vector index has reached its configured capacity")
            connection.execute(
                "INSERT INTO memory_vectors(memory_id, dimension, vector, updated_at) VALUES (?, ?, ?, datetime('now')) "
                "ON CONFLICT(memory_id) DO UPDATE SET dimension=excluded.dimension, vector=excluded.vector, updated_at=excluded.updated_at",
                (int(memory_id), len(vector), packed),
            )

    def delete(self, memory_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM memory_vectors WHERE memory_id=?", (int(memory_id),))
            return cursor.rowcount == 1

    def clear(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM memory_vectors")

    def count(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM memory_vectors").fetchone()[0])

    def search(self, query: str, limit: int = 10, min_score: float = -1.0) -> list[VectorMatch]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Semantic query must be a non-empty string")
        limit = max(1, min(int(limit), 50))
        if not -1.0 <= min_score <= 1.0:
            raise ValueError("Minimum similarity must be between -1 and 1")
        needle = self.embedder.embed(query)
        matches: list[VectorMatch] = []
        with self._connect() as connection:
            rows = connection.execute("SELECT memory_id, dimension, vector FROM memory_vectors").fetchall()
        for row in rows:
            dimension = int(row["dimension"])
            if dimension != len(needle):
                continue
            values = struct.unpack(f"!{dimension}f", row["vector"])
            score = sum(left * right for left, right in zip(needle, values))
            if score >= min_score:
                matches.append(VectorMatch(int(row["memory_id"]), float(score)))
        matches.sort(key=lambda match: match.score, reverse=True)
        return matches[:limit]


__all__ = ["EmbeddingProvider", "HashEmbedding", "SQLiteVectorStore", "VectorMatch"]
