"""Minimal Gemini REST adapter.

The adapter uses the public generateContent HTTP shape and keeps provider-specific
translation isolated from the rest of the application.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

import requests

from .schemas import ChatMessage, LLMResponse, ToolCall, ToolSpec


class GeminiClient:
    provider_name = "gemini"

    def __init__(self, api_key: str, model: str, timeout_seconds: float = 30.0) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def complete(self, messages: list[ChatMessage], tools: list[ToolSpec]) -> LLMResponse:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        body: dict[str, Any] = {
            "contents": [_to_gemini_message(message) for message in messages],
        }
        if tools:
            body["tools"] = [{"functionDeclarations": [_to_gemini_declaration(tool) for tool in tools]}]

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
            f"?key={self.api_key}"
        )
        response = requests.post(url, json=body, timeout=self.timeout_seconds)
        if response.status_code >= 400:
            raise RuntimeError(f"Gemini HTTP {response.status_code}: {response.text[:500]}")
        return _parse_response(response.json())


def _to_gemini_message(message: ChatMessage) -> dict[str, Any]:
    role = "model" if message.role == "assistant" else "user"
    parts: list[dict[str, Any]] = []
    if message.content:
        parts.append({"text": message.content})
    if message.role == "tool":
        try:
            response = json.loads(message.content)
        except (TypeError, json.JSONDecodeError):
            response = {"result": message.content}
        return {
            "role": "user",
            "parts": [{
                "functionResponse": {
                    "name": message.name or "tool",
                    "response": response,
                }
            }],
        }
    return {"role": role, "parts": parts or [{"text": ""}]}


def _to_gemini_declaration(tool: ToolSpec) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": _gemini_schema(tool.parameters),
    }


def _gemini_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Translate common JSON Schema primitive types to Gemini's schema form."""
    result: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "type" and isinstance(value, str):
            result[key] = value.upper()
        elif key == "properties" and isinstance(value, Mapping):
            result[key] = {name: _gemini_schema(child) for name, child in value.items()}
        elif key == "items" and isinstance(value, Mapping):
            result[key] = _gemini_schema(value)
        elif key in {"additionalProperties", "maxLength"}:
            continue
        else:
            result[key] = value
    return result


def _parse_response(payload: Mapping[str, Any]) -> LLMResponse:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini response did not include a candidate")
    parts = ((candidates[0].get("content") or {}).get("parts") or [])
    text_parts: list[str] = []
    calls: list[ToolCall] = []
    for index, part in enumerate(parts):
        if part.get("text"):
            text_parts.append(str(part["text"]))
        function_call = part.get("functionCall")
        if function_call:
            calls.append(
                ToolCall(
                    id=f"gemini-call-{index}",
                    name=str(function_call.get("name", "")),
                    arguments=dict(function_call.get("args") or {}),
                )
            )
    return LLMResponse(provider="gemini", content="\n".join(text_parts), tool_calls=tuple(calls), raw=payload)


__all__ = ["GeminiClient"]
