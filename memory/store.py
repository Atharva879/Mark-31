"""Small SQLite memory store for explicit user-controlled facts and notes."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path


class MemoryStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL CHECK(kind IN ('fact', 'note')),
                    key TEXT,
                    content TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'user',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(kind, key)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_content ON memories(content)"
            )

    def remember_note(self, content: str, tags: str = "", source: str = "user") -> int:
        content = _bounded_text(content, "content", 8_000)
        now = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO memories(kind, key, content, tags, source, created_at, updated_at) "
                "VALUES ('note', NULL, ?, ?, ?, ?, ?)",
                (content, tags[:500], source[:200], now, now),
            )
            return int(cursor.lastrowid)

    def remember_fact(self, key: str, content: str, tags: str = "", source: str = "user") -> int:
        key = _bounded_text(key, "key", 300)
        content = _bounded_text(content, "content", 8_000)
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO memories(kind, key, content, tags, source, created_at, updated_at)
                VALUES ('fact', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(kind, key) DO UPDATE SET
                    content=excluded.content,
                    tags=excluded.tags,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                (key, content, tags[:500], source[:200], now, now),
            )
            row = connection.execute(
                "SELECT id FROM memories WHERE kind='fact' AND key=?", (key,)
            ).fetchone()
            return int(row["id"])

    def recall(self, query: str, limit: int = 10) -> list[dict[str, str | int]]:
        query = _bounded_text(query, "query", 500)
        limit = max(1, min(int(limit), 50))
        pattern = f"%{query}%"
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, kind, key, content, tags, source, created_at, updated_at
                FROM memories
                WHERE content LIKE ? OR COALESCE(key, '') LIKE ? OR tags LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (pattern, pattern, pattern, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def all_memories(self, limit: int = 100_000) -> list[dict[str, str | int]]:
        limit = max(1, min(int(limit), 100_000))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, kind, key, content, tags, source, created_at, updated_at "
                "FROM memories ORDER BY id ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def recent(self, limit: int = 10) -> list[dict[str, str | int]]:
        limit = max(1, min(int(limit), 50))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, kind, key, content, tags, source, created_at, updated_at "
                "FROM memories ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def forget(self, memory_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM memories WHERE id=?", (int(memory_id),))
            return cursor.rowcount == 1


def _bounded_text(value: str, label: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    if len(value) > limit:
        raise ValueError(f"{label} exceeds the configured size limit")
    return value.strip()


def _now() -> str:
    return datetime.now(UTC).isoformat()


__all__ = ["MemoryStore"]
