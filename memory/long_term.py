"""Durable hybrid memory combining SQLite records with a local vector index."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .store import MemoryStore
from .vector_store import SQLiteVectorStore


class LongTermMemory:
    def __init__(self, memory_path: Path, vector_path: Path | None = None) -> None:
        self.store = MemoryStore(memory_path)
        self.vectors = SQLiteVectorStore(vector_path or Path(memory_path).with_suffix(".vectors.db"))

    def remember_note(self, content: str, tags: str = "", source: str = "user") -> int:
        memory_id = self.store.remember_note(content, tags=tags, source=source)
        self.vectors.upsert(memory_id, f"{content} {tags}")
        return memory_id

    def remember_fact(self, key: str, content: str, tags: str = "", source: str = "user") -> int:
        memory_id = self.store.remember_fact(key, content, tags=tags, source=source)
        self.vectors.upsert(memory_id, f"{key} {content} {tags}")
        return memory_id

    def recall(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        return self.store.recall(query, limit)

    def semantic_recall(self, query: str, limit: int = 10, min_score: float = 0.1) -> list[dict[str, Any]]:
        matches = self.vectors.search(query, limit=limit, min_score=min_score)
        by_id = {int(item["id"]): item for item in self.store.all_memories(limit=100_000)}
        results: list[dict[str, Any]] = []
        for match in matches:
            item = by_id.get(match.memory_id)
            if item is not None:
                results.append({**item, "similarity": round(match.score, 6)})
        return results

    def recent(self, limit: int = 10) -> list[dict[str, Any]]:
        return self.store.recent(limit)

    def vector_exists(self, memory_id: int) -> bool:
        return self.vectors.contains(memory_id)

    def forget(self, memory_id: int) -> bool:
        deleted = self.store.forget(memory_id)
        self.vectors.delete(memory_id)
        return deleted

    def reindex(self) -> int:
        self.vectors.clear()
        memories = self.store.all_memories(limit=100_000)
        for item in memories:
            searchable = f"{item.get('key') or ''} {item['content']} {item.get('tags') or ''}"
            self.vectors.upsert(int(item["id"]), searchable)
        return len(memories)

    def stats(self) -> dict[str, int]:
        total = len(self.store.all_memories(limit=100_000))
        return {"memory_records": total, "vector_records": self.vectors.count()}


__all__ = ["LongTermMemory"]
