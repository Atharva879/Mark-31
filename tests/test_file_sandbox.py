from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from audit import AuditLogger
from skills.code_sandbox import CodeSandbox
from skills.files import ScopedFileManager


def test_advanced_file_search_metadata_and_hash(tmp_path: Path):
    nested = tmp_path / "nested"
    nested.mkdir()
    target = nested / "hello.txt"
    target.write_text("hello", encoding="utf-8")
    manager = ScopedFileManager((tmp_path,))

    assert manager.find_files("*.txt") == [str(target)]
    metadata = manager.metadata(str(target))
    assert metadata["size_bytes"] == 5
    assert metadata["is_file"] is True
    assert manager.sha256(str(target)) == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def test_archive_inspection_does_not_extract_and_flags_traversal(tmp_path: Path):
    archive_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("safe/readme.txt", "ok")
        archive.writestr("../escape.txt", "blocked if extracted")
    manager = ScopedFileManager((tmp_path,))

    result = manager.inspect_archive(str(archive_path))

    assert result["entry_count"] == 2
    assert any(item["unsafe_path"] for item in result["entries"])
    assert not (tmp_path / "safe" / "readme.txt").exists()


def test_file_operations_remain_root_scoped(tmp_path: Path):
    manager = ScopedFileManager((tmp_path,))
    with pytest.raises(PermissionError, match="outside"):
        manager.metadata(str(tmp_path.parent / "outside.txt"))


def test_sandbox_runs_pure_calculation_and_rejects_io():
    sandbox = CodeSandbox(timeout_seconds=2, max_output_chars=100)
    result = sandbox.execute("print(sum(range(5)))")
    assert result["status"] == "completed"
    assert result["stdout"].strip() == "10"

    with pytest.raises(PermissionError, match="Import"):
        sandbox.execute("import os")
    with pytest.raises(PermissionError, match="open"):
        sandbox.execute("open('x', 'w')")


def test_sandbox_timeout_and_output_limits():
    sandbox = CodeSandbox(timeout_seconds=0.2, max_output_chars=10)
    timeout_result = sandbox.execute("while True: pass")
    assert timeout_result["status"] == "timed_out"
    output_result = CodeSandbox(timeout_seconds=2, max_output_chars=10).execute("print('x' * 100)")
    assert output_result["truncated"] is True
    assert len(output_result["stdout"]) <= 10


def test_audit_redacts_sandbox_source(tmp_path: Path):
    log_path = tmp_path / "audit.jsonl"
    AuditLogger(log_path).record("tool_requested", arguments={"code": "print('private source')"})
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert "private source" not in log_path.read_text(encoding="utf-8")
    assert payload["arguments"]["code"].startswith("[SHA256:")
