from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from agent_orchestrator import DelegationError, MultiAgentCoordinator
from audit import AuditLogger
from dispatcher import Dispatcher, ToolRegistry
from llm.schemas import RiskTier, ToolSpec


class FakeRouter:
    def __init__(self, delay: float = 0.0):
        self.delay = delay
        self.calls: list[tuple[str, list[str]]] = []
        self.lock = threading.Lock()

    def run_tool_loop(self, prompt, tools, dispatcher, system_prompt=""):
        if self.delay:
            time.sleep(self.delay)
        with self.lock:
            self.calls.append((prompt, [tool.name for tool in tools]))
        return f"done: {prompt}"


def _coordinator(tmp_path: Path, router=None, **kwargs):
    return MultiAgentCoordinator(router or FakeRouter(), AuditLogger(tmp_path / "audit.jsonl"), **kwargs)


def test_delegation_runs_bounded_roles_and_excludes_sensitive_tools(tmp_path: Path):
    router = FakeRouter()
    coordinator = _coordinator(tmp_path, router)
    tools = [
        ToolSpec("web_search", "search", {"type": "object"}, RiskTier.SAFE, lambda: None),
        ToolSpec("run_shell_command", "shell", {"type": "object"}, RiskTier.SENSITIVE, lambda: None),
        ToolSpec("delegate_subtasks", "delegate", {"type": "object"}, RiskTier.MODERATE, lambda: None),
    ]
    result = coordinator.delegate(
        [{"task_id": "research", "role": "researcher", "prompt": "Find current facts"}],
        tools,
        Dispatcher(ToolRegistry(), AuditLogger(tmp_path / "dispatch.jsonl")),
    )

    assert result["completed"] == 1
    assert result["failed"] == 0
    assert router.calls[0][1] == ["web_search"]


def test_delegation_validates_roles_limits_and_duplicate_ids(tmp_path: Path):
    coordinator = _coordinator(tmp_path, max_subtasks=2)
    dispatcher = Dispatcher(ToolRegistry(), AuditLogger(tmp_path / "dispatch.jsonl"))
    with pytest.raises(DelegationError, match="Unknown agent role"):
        coordinator.delegate([{"role": "hacker", "prompt": "x"}], [], dispatcher)
    with pytest.raises(DelegationError, match="between 1 and 2"):
        coordinator.delegate([], [], dispatcher)
    with pytest.raises(DelegationError, match="unique"):
        coordinator.delegate(
            [{"task_id": "same", "role": "researcher", "prompt": "a"}, {"task_id": "same", "role": "researcher", "prompt": "b"}],
            [],
            dispatcher,
        )


def test_delegation_contains_failures_and_writes_audit(tmp_path: Path):
    class BrokenRouter(FakeRouter):
        def run_tool_loop(self, *args, **kwargs):
            raise RuntimeError("provider failed")

    audit_path = tmp_path / "audit.jsonl"
    coordinator = MultiAgentCoordinator(BrokenRouter(), AuditLogger(audit_path))
    dispatcher = Dispatcher(ToolRegistry(), AuditLogger(tmp_path / "dispatch.jsonl"))
    result = coordinator.delegate([{"role": "researcher", "prompt": "Look up facts"}], [], dispatcher)

    assert result["failed"] == 1
    assert result["results"][0]["status"] == "failed"
    audit = audit_path.read_text(encoding="utf-8")
    assert "delegation_started" in audit
    assert "subtask_failed" in audit
    assert "Look up facts" not in audit


def test_delegation_caps_prompt_and_result(tmp_path: Path):
    coordinator = _coordinator(tmp_path, max_prompt_chars=100, max_result_chars=1000)
    dispatcher = Dispatcher(ToolRegistry(), AuditLogger(tmp_path / "dispatch.jsonl"))
    with pytest.raises(DelegationError, match="prompt"):
        coordinator.delegate([{"role": "researcher", "prompt": "x" * 101}], [], dispatcher)


def test_runtime_registers_moderate_delegate_tool(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("JARVIS_MEMORY_DB", str(tmp_path / "memory.db"))
    monkeypatch.setenv("JARVIS_VECTOR_DB", str(tmp_path / "vectors.db"))
    from main import build_runtime
    from config import Settings

    _, _, registry = build_runtime(Settings.from_env())
    spec = next(tool for tool in registry.all() if tool.name == "delegate_subtasks")
    assert spec.risk is RiskTier.MODERATE
    assert "subtasks" in spec.parameters["required"]
