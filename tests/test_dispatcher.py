from __future__ import annotations

import json

import pytest

from audit import AuditLogger
from dispatcher import Dispatcher, ToolRegistry, ToolValidationError
from llm.schemas import RiskTier, ToolSpec


def make_dispatcher(tmp_path, confirm=None):
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="safe_tool",
            description="A safe test action",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            risk=RiskTier.SAFE,
            handler=lambda: "ok",
        )
    )
    registry.register(
        ToolSpec(
            name="sensitive_tool",
            description="A sensitive test action",
            parameters={
                "type": "object",
                "properties": {"target": {"type": "string"}},
                "required": ["target"],
                "additionalProperties": False,
            },
            risk=RiskTier.SENSITIVE,
            handler=lambda target: f"changed {target}",
        )
    )
    return Dispatcher(registry, AuditLogger(tmp_path / "audit.jsonl"), confirm=confirm)


def test_unknown_tool_is_rejected(tmp_path):
    dispatcher = make_dispatcher(tmp_path)
    with pytest.raises(ToolValidationError, match="Unknown tool"):
        dispatcher.dispatch("not_registered", {})


def test_unknown_arguments_are_rejected(tmp_path):
    dispatcher = make_dispatcher(tmp_path)
    with pytest.raises(ToolValidationError, match="Unknown arguments"):
        dispatcher.dispatch("safe_tool", {"shell": "do not run"})


def test_sensitive_tool_cannot_execute_without_confirmation(tmp_path):
    called = []
    dispatcher = make_dispatcher(tmp_path, confirm=lambda prompt: called.append(prompt) or False)

    result = dispatcher.dispatch("sensitive_tool", {"target": "important.txt"})

    assert result.executed is False
    assert result.confirmation_required is True
    assert called and "important.txt" in called[0]


def test_sensitive_tool_runs_only_after_confirmation(tmp_path):
    dispatcher = make_dispatcher(tmp_path, confirm=lambda _prompt: True)

    result = dispatcher.dispatch("sensitive_tool", {"target": "important.txt"})

    assert result.executed is True
    assert result.output == "changed important.txt"
    events = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert [event["event"] for event in events] == [
        "tool_requested",
        "confirmation_result",
        "tool_completed",
    ]
