from __future__ import annotations

from pathlib import Path

import pytest

from memory.store import MemoryStore
from skills.files import ScopedFileManager


def test_memory_persists_facts_notes_and_forget(tmp_path):
    database = tmp_path / "memory.db"
    first = MemoryStore(database)
    fact_id = first.remember_fact("preferred_editor", "VS Code", tags="work")
    note_id = first.remember_note("Prepare the client proposal", tags="work")

    second = MemoryStore(database)
    assert second.recall("VS Code")[0]["id"] == fact_id
    assert second.recall("proposal")[0]["id"] == note_id
    assert second.forget(fact_id) is True
    assert second.recall("VS Code") == []


def test_memory_updates_fact_in_place(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    first_id = store.remember_fact("timezone", "Asia/Kolkata")
    second_id = store.remember_fact("timezone", "UTC")

    assert first_id == second_id
    assert store.recall("timezone")[0]["content"] == "UTC"


def test_file_manager_rejects_paths_outside_root(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    manager = ScopedFileManager([root])

    with pytest.raises(PermissionError):
        manager.read_text(outside)


def test_file_manager_reads_writes_and_moves_within_roots(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    manager = ScopedFileManager([root])

    manager.write_text("notes/today.txt", "hello")
    assert manager.read_text("notes/today.txt") == "hello"
    moved = manager.move("notes/today.txt", "archive/today.txt")
    assert Path(moved).read_text(encoding="utf-8") == "hello"


def test_file_manager_rejects_binary_and_large_files(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    binary = root / "binary.bin"
    binary.write_bytes(b"a\x00b")
    binary_manager = ScopedFileManager([root], max_read_bytes=10)
    with pytest.raises(ValueError, match="Binary"):
        binary_manager.read_text(binary)

    small_manager = ScopedFileManager([root], max_read_bytes=2)
    with pytest.raises(ValueError, match="write limit"):
        small_manager.write_text("large.txt", "abc")
