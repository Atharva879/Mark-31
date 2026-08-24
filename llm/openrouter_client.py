"""OpenRouter OpenAI-compatible fallback adapter."""

from __future__ import annotations

import json
from typing import Any, Mapping

import requests

from .schemas import ChatMessage, LLMResponse, ToolCall, ToolSpec


class OpenRouterClient:
    provider_name = "openrouter"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
        base_url: str = "https://openrouter.ai/api/v1/chat/completions",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url

    def complete(self, messages: list[ChatMessage], tools: list[ToolSpec]) -> LLMResponse:
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [message.as_dict() for message in messages],
        }
        if tools:
            body["tools"] = [tool.as_provider_schema() for tool in tools]
            body["tool_choice"] = "auto"
        response = requests.post(
            self.base_url,
            json=body,
            timeout=self.timeout_seconds,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost",
                "X-Title": "Jarvis Local Agent",
            },
        )
        if response.status_code >= 400:
            raise RuntimeError(f"OpenRouter HTTP {response.status_code}: {response.text[:500]}")
        return _parse_response(response.json())


def _parse_response(payload: Mapping[str, Any]) -> LLMResponse:
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("OpenRouter response did not include a choice")
    message = choices[0].get("message") or {}
    calls: list[ToolCall] = []
    for index, call in enumerate(message.get("tool_calls") or []):
        function = call.get("function") or {}
        arguments = function.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError as exc:
                raise RuntimeError("OpenRouter returned invalid JSON tool arguments") from exc
        if not isinstance(arguments, dict):
            raise RuntimeError("OpenRouter tool arguments must be a JSON object")
        calls.append(
            ToolCall(
                id=str(call.get("id") or f"openrouter-call-{index}"),
                name=str(function.get("name", "")),
                arguments=arguments,
            )
        )
    return LLMResponse(
        provider="openrouter",
        content=str(message.get("content") or ""),
        tool_calls=tuple(calls),
        raw=payload,
    )


__all__ = ["OpenRouterClient"]
