import pytest

from automation_orchestrator import AutomationOrchestrator


class FakeAdapter:
    def __init__(self):
        self.calls = []

    def click(self, target):
        self.calls.append(("click", target))

    def type_text(self, text):
        self.calls.append(("type_text", text))


def test_grants_and_runs_only_approved_adapter_actions():
    adapter = FakeAdapter()
    orchestrator = AutomationOrchestrator({"notepad": adapter})
    grant = orchestrator.grant("notepad", "notepad.exe", {"click", "type_text"}, unattended=True)
    assert grant["unattended"] is True
    result = orchestrator.run("notepad", [{"action": "click", "arguments": {"target": "Editor"}}])
    assert result["completed"] == 1
    assert adapter.calls == [("click", "Editor")]
    with pytest.raises(PermissionError):
        orchestrator.run("notepad", [{"action": "close", "arguments": {}}])


def test_missing_adapter_and_missing_grant_fail_closed():
    orchestrator = AutomationOrchestrator({})
    with pytest.raises(ValueError):
        orchestrator.grant("unknown", "unknown.exe", {"click"})
    with pytest.raises(PermissionError):
        orchestrator.run("unknown", [{"action": "click"}])


def test_emergency_stop_latches_until_rearm():
    adapter = FakeAdapter()
    orchestrator = AutomationOrchestrator({"notepad": adapter})
    orchestrator.grant("notepad", "notepad.exe", {"click"})
    orchestrator.stop_all()
    result = orchestrator.run("notepad", [{"action": "click", "arguments": {"target": "Editor"}}])
    assert result["completed"] == 0
    assert result["stopped"] is True
    orchestrator.arm()
    assert (
        orchestrator.run("notepad", [{"action": "click", "arguments": {"target": "Editor"}}])[
            "completed"
        ]
        == 1
    )
