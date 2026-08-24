"""Provider-neutral message and tool-call models used by the dispatcher."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, Mapping


class RiskTier(StrEnum):
    SAFE = "SAFE"
    MODERATE = "MODERATE"
    SENSITIVE = "SENSITIVE"


@dataclass(frozen=True)
class ToolSpec:
    """A registered callable and the schema the model may use to invoke it."""

    name: str
    description: str
    parameters: Mapping[str, Any]
    risk: RiskTier
    handler: Callable[..., Any]
    confirmation_required: bool = False

    def as_provider_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": dict(self.parameters),
            },
        }


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LLMResponse:
    provider: str
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    raw: Any = None


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str
    tool_call_id: str | None = None
    name: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_call_id is not None:
            result["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            result["name"] = self.name
        if self.tool_calls:
            result["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, separators=(",", ":")),
                    },
                }
                for call in self.tool_calls
            ]
        return result


@dataclass(frozen=True)
class DispatchResult:
    tool_name: str
    risk: RiskTier
    executed: bool
    output: Any = None
    error: str | None = None
    confirmation_required: bool = False


@dataclass
class Conversation:
    """Bounded message history for one tool-calling request."""

    messages: list[ChatMessage] = field(default_factory=list)

    def append(self, message: ChatMessage) -> None:
        self.messages.append(message)

    def as_dicts(self) -> list[dict[str, Any]]:
        return [message.as_dict() for message in self.messages]


__all__ = [
    "ChatMessage",
    "Conversation",
    "DispatchResult",
    "LLMResponse",
    "RiskTier",
    "ToolCall",
    "ToolSpec",
]
