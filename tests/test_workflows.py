from __future__ import annotations

from pathlib import Path

import pytest

from llm.schemas import RiskTier, ToolSpec
from workflows import SafeWorkflowEngine, WorkflowStep, WorkflowStore


class Result:
    error = None


class Registry:
    def __init__(self, tools):
        self.tools = {tool.name: tool for tool in tools}

    def get(self, name):
        return self.tools.get(name)


class Dispatcher:
    def __init__(self):
        self.calls = []

    def dispatch(self, name, arguments):
        self.calls.append((name, arguments))
        return Result()


def test_safe_workflow_preview_and_run(tmp_path: Path):
    tool = ToolSpec("echo", "safe", {"type": "object"}, RiskTier.SAFE, lambda: None)
    store = WorkflowStore(tmp_path / "workflows.db")
    workflow = store.create("Morning status", [WorkflowStep("echo", {})])
    dispatcher = Dispatcher()
    engine = SafeWorkflowEngine(store, Registry([tool]), dispatcher)
    assert engine.preview(workflow.workflow_id)[0]["risk"] == "SAFE"
    assert len(engine.run(workflow.workflow_id)) == 1
    assert dispatcher.calls == [("echo", {})]


def test_workflows_reject_unsafe_tools_and_disabled_runs(tmp_path: Path):
    unsafe = ToolSpec("shell", "unsafe", {"type": "object"}, RiskTier.SENSITIVE, lambda: None)
    store = WorkflowStore(tmp_path / "workflows.db")
    workflow = store.create("Unsafe", [WorkflowStep("shell", {})])
    engine = SafeWorkflowEngine(store, Registry([unsafe]), Dispatcher())
    with pytest.raises(PermissionError, match="SAFE"):
        engine.run(workflow.workflow_id)
    store.set_enabled(workflow.workflow_id, False)
    with pytest.raises(PermissionError, match="disabled"):
        engine.run(workflow.workflow_id)


def test_workflow_step_count_is_bounded(tmp_path: Path):
    store = WorkflowStore(tmp_path / "workflows.db")
    with pytest.raises(ValueError, match="between 1 and 10"):
        store.create("Too many", [WorkflowStep("echo", {})] * 11)
