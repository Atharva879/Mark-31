from __future__ import annotations

from pathlib import Path

from memory.long_term import LongTermMemory
from memory.vector_store import HashEmbedding, SQLiteVectorStore


def test_hash_embedding_is_deterministic_and_normalized():
    embedder = HashEmbedding(128)
    first = embedder.embed("blue bicycle")
    second = embedder.embed("blue bicycle")

    assert first == second
    assert abs(sum(value * value for value in first) - 1.0) < 1e-6


def test_long_term_memory_persists_vectors_and_semantic_recall(tmp_path: Path):
    memory_path = tmp_path / "memory.db"
    vector_path = tmp_path / "vectors.db"
    memory = LongTermMemory(memory_path, vector_path)
    bicycle_id = memory.remember_note("The blue bicycle is stored in the garage", tags="vehicle")
    memory.remember_note("The quarterly tax filing deadline is in April", tags="finance")

    reopened = LongTermMemory(memory_path, vector_path)
    results = reopened.semantic_recall("Where is the bicycle?", limit=5, min_score=0.1)

    assert results
    assert results[0]["id"] == bicycle_id
    assert results[0]["similarity"] > 0.1
    assert reopened.stats() == {"memory_records": 2, "vector_records": 2}


def test_forget_removes_vector_and_reindex_repairs_missing_vectors(tmp_path: Path):
    memory = LongTermMemory(tmp_path / "memory.db", tmp_path / "vectors.db")
    memory_id = memory.remember_note("A recoverable note")
    assert memory.forget(memory_id) is True
    assert memory.vectors.count() == 0

    second_id = memory.remember_note("A note that will be reindexed")
    memory.vectors.delete(second_id)
    assert memory.vectors.count() == 0
    assert memory.reindex() == 1
    assert memory.vectors.count() == 1


def test_vector_store_bounds_search_limits(tmp_path: Path):
    store = SQLiteVectorStore(tmp_path / "vectors.db")
    store.upsert(1, "hello world")
    results = store.search("hello", limit=0)
    assert len(results) == 1
