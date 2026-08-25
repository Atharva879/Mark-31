from pathlib import Path

import pytest

from task_loops import AutonomousLoopController, TaskLoopStore


class Dispatcher:
    def __init__(self):
        self.calls = []

    def execute(self, tool, arguments):
        self.calls.append((tool, arguments))
        return {"ok": True}


def test_loop_persists_and_runs_safe_tools(tmp_path: Path):
    store = TaskLoopStore(tmp_path / "loops.db")
    loop_id = store.create("heartbeat", "echo_status", "{}", 60)
    dispatcher = Dispatcher()
    result = AutonomousLoopController(store, dispatcher).run(loop_id, "echo_status", {}, "SAFE", 3)
    assert result["completed"] == 3
    assert len(dispatcher.calls) == 3
    assert store.list()[0]["name"] == "heartbeat"


def test_loop_rejects_sensitive_tools_and_honors_stop(tmp_path: Path):
    store = TaskLoopStore(tmp_path / "loops.db")
    controller = AutonomousLoopController(store, Dispatcher())
    with pytest.raises(PermissionError):
        controller.run("x", "send_message", {}, "SENSITIVE")
    controller.stop_all()
    assert controller.run("x", "echo_status", {}, "SAFE", 4)["completed"] == 0
