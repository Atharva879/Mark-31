from __future__ import annotations

from config import Settings
from dispatcher import Dispatcher, ToolRegistry
from audit import AuditLogger
from llm.router import AllProvidersFailed, LLMRouter
from llm.schemas import ChatMessage, LLMResponse, RiskTier, ToolCall, ToolSpec
from skills.mock_tools import echo_status


class FakeProvider:
    def __init__(self, name, responses=None, error=None):
        self.provider_name = name
        self.responses = list(responses or [])
        self.error = error
        self.calls = 0

    def complete(self, messages, tools):
        self.calls += 1
        if self.error:
            raise self.error
        return self.responses.pop(0)


def settings(**overrides):
    values = dict(provider_order=("gemini", "openrouter"), max_retries_per_provider=0)
    values.update(overrides)
    return Settings(**values)


def test_primary_provider_is_used():
    primary = FakeProvider("gemini", [LLMResponse("gemini", content="hello")])
    fallback = FakeProvider("openrouter", [LLMResponse("openrouter", content="fallback")])
    router = LLMRouter({"gemini": primary, "openrouter": fallback}, settings())

    result = router.complete([ChatMessage("user", "hello")], [])

    assert result.content == "hello"
    assert primary.calls == 1
    assert fallback.calls == 0


def test_primary_failure_falls_back_and_records_event():
    primary = FakeProvider("gemini", error=TimeoutError("timed out"))
    fallback = FakeProvider("openrouter", [LLMResponse("openrouter", content="recovered")])
    router = LLMRouter({"gemini": primary, "openrouter": fallback}, settings())

    result = router.complete([ChatMessage("user", "hello")], [])

    assert result.provider == "openrouter"
    assert result.content == "recovered"
    assert [event.provider for event in router.events] == ["gemini", "openrouter"]
    assert router.events[0].success is False


def test_all_provider_failures_are_reported():
    router = LLMRouter(
        {
            "gemini": FakeProvider("gemini", error=RuntimeError("one")),
            "openrouter": FakeProvider("openrouter", error=RuntimeError("two")),
        },
        settings(),
    )

    try:
        router.complete([ChatMessage("user", "hello")], [])
    except AllProvidersFailed as exc:
        assert "gemini" in str(exc)
        assert "openrouter" in str(exc)
    else:
        raise AssertionError("Expected AllProvidersFailed")


def test_tool_loop_executes_registered_tool_and_returns_follow_up(tmp_path):
    tool = ToolSpec(
        name="echo_status",
        description="Echo a status",
        parameters={
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
            "additionalProperties": False,
        },
        risk=RiskTier.SAFE,
        handler=echo_status,
    )
    registry = ToolRegistry()
    registry.register(tool)
    dispatcher = Dispatcher(registry, AuditLogger(tmp_path / "audit.jsonl"))
    provider = FakeProvider(
        "gemini",
        [
            LLMResponse(
                "gemini",
                tool_calls=(ToolCall("call-1", "echo_status", {"message": "ready"}),),
            ),
            LLMResponse("gemini", content="The system is ready."),
        ],
    )
    router = LLMRouter({"gemini": provider}, settings(provider_order=("gemini",)))

    result = router.run_tool_loop("check status", [tool], dispatcher)

    assert result == "The system is ready."
    assert provider.calls == 2
