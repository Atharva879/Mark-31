from __future__ import annotations

from pathlib import Path

import pytest

from knowledge import KnowledgeStore


def test_import_search_and_refresh_with_citation(tmp_path: Path):
    root = tmp_path / "allowed"
    root.mkdir()
    source = root / "notes.md"
    source.write_text(
        "Jarvis uses local-first memory.\nThe workspace has citations.", encoding="utf-8"
    )
    store = KnowledgeStore(tmp_path / "knowledge.db", [root])
    imported = store.import_source(str(source))
    assert imported["title"] == "notes.md"
    results = store.search("local-first citations")
    assert results[0]["source_id"] == imported["source_id"]
    assert "notes.md" in results[0]["citation"]
    source.write_text("Updated knowledge workspace", encoding="utf-8")
    store.import_source(str(source))
    assert len(store.list_sources()) == 1
    assert store.search("updated")[0]["title"] == "notes.md"


def test_import_rejects_outside_and_unsupported_files(tmp_path: Path):
    root = tmp_path / "allowed"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("private", encoding="utf-8")
    unsupported = root / "program.py"
    unsupported.write_text("print('no')", encoding="utf-8")
    store = KnowledgeStore(tmp_path / "knowledge.db", [root])
    with pytest.raises(PermissionError):
        store.import_source(str(outside))
    with pytest.raises(ValueError):
        store.import_source(str(unsupported))


def test_delete_is_explicit_and_bounded(tmp_path: Path):
    root = tmp_path / "allowed"
    root.mkdir()
    source = root / "a.txt"
    source.write_text("bounded source", encoding="utf-8")
    store = KnowledgeStore(tmp_path / "knowledge.db", [root])
    source_id = store.import_source(str(source))["source_id"]
    assert store.delete(str(source_id)) is True
    assert store.delete(str(source_id)) is False
