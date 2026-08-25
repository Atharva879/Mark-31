from __future__ import annotations

from pathlib import Path

import pytest

from skills.browser import ReadOnlyBrowser
from skills.shell import SafeCommandExecutor


def test_shell_executes_allowlisted_command_without_shell_interpretation(tmp_path: Path):
    executor = SafeCommandExecutor({"echo"}, (tmp_path,), timeout_seconds=2, max_output_chars=100)

    result = executor.execute("echo hello", str(tmp_path))

    assert result["returncode"] == 0
    assert result["stdout"].strip() == "hello"
    assert result["timed_out"] is False


def test_shell_rejects_unallowlisted_and_interpreter_commands(tmp_path: Path):
    executor = SafeCommandExecutor({"echo", "python"}, (tmp_path,))
    with pytest.raises(PermissionError, match="not allowlisted"):
        executor.execute("rm -rf .", str(tmp_path))
    with pytest.raises(PermissionError, match="evaluation"):
        executor.execute("python -c print(1)", str(tmp_path))


def test_shell_rejects_out_of_scope_working_directory(tmp_path: Path):
    executor = SafeCommandExecutor({"echo"}, (tmp_path,))
    with pytest.raises(PermissionError, match="outside"):
        executor.execute("echo hello", str(tmp_path.parent))


def test_browser_returns_read_only_metadata():
    class FakeWebClient:
        def fetch_url(self, url, max_chars=12_000):
            return {"url": url, "content": "Example page", "status_code": 200}

        def search(self, query, max_results=None):
            return [{"title": "Result", "url": "https://example.com", "snippet": query}]

    browser = ReadOnlyBrowser(FakeWebClient())
    page = browser.navigate("https://example.com")

    assert page["mode"] == "read_only"
    assert page["scripts_executed"] is False
    assert page["forms_submitted"] is False
    assert page["downloads_started"] is False
    assert browser.search("test")[0]["title"] == "Result"


def test_runtime_requires_confirmation_for_shell_tool(tmp_path):
    from config import Settings
    from main import build_runtime

    settings = Settings(audit_log_path=tmp_path / "audit.jsonl", memory_db_path=tmp_path / "memory.db")
    _router, dispatcher, registry = build_runtime(settings)

    result = dispatcher.dispatch("run_shell_command", {"command": "echo blocked"})

    assert result.executed is False
    assert result.confirmation_required is True
