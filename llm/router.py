"""Provider-independent routing and bounded tool-calling orchestration."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

from config import Settings
from dispatcher import Dispatcher

from .schemas import ChatMessage, LLMResponse, ToolSpec

logger = logging.getLogger(__name__)


class Provider(Protocol):
    provider_name: str

    def complete(self, messages: list[ChatMessage], tools: list[ToolSpec]) -> LLMResponse:
        ...


class AllProvidersFailed(RuntimeError):
    """Raised when every configured provider fails for the same request."""

    def __init__(self, failures: list[tuple[str, str]]) -> None:
        self.failures = failures
        detail = "; ".join(f"{provider}: {error}" for provider, error in failures)
        super().__init__(f"All LLM providers failed: {detail}")


@dataclass(frozen=True)
class RouteEvent:
    provider: str
    attempt: int
    success: bool
    error: str | None = None


class LLMRouter:
    """Try providers in configured order, with bounded retries per provider."""

    def __init__(
        self,
        providers: dict[str, Provider],
        settings: Settings,
        sleep_fn: Any = time.sleep,
    ) -> None:
        self.providers = providers
        self.settings = settings
        self.sleep_fn = sleep_fn
        self.events: list[RouteEvent] = []

    def complete(self, messages: list[ChatMessage], tools: list[ToolSpec]) -> LLMResponse:
        if not messages:
            raise ValueError("At least one message is required")
        failures: list[tuple[str, str]] = []
        for provider_name in self.settings.provider_order:
            provider = self.providers.get(provider_name)
            if provider is None:
                failures.append((provider_name, "provider is not initialized"))
                self.events.append(RouteEvent(provider_name, 0, False, "provider is not initialized"))
                continue
            for attempt in range(1, self.settings.max_retries_per_provider + 2):
                try:
                    response = provider.complete(messages, tools)
                    self.events.append(RouteEvent(provider_name, attempt, True))
                    if failures:
                        logger.warning("LLM provider failover selected %s after %s", provider_name, failures)
                    return response
                except Exception as exc:  # provider errors must not stop fallback
                    error = _safe_error(exc)
                    failures.append((provider_name, error))
                    self.events.append(RouteEvent(provider_name, attempt, False, error))
                    logger.warning("LLM provider %s attempt %d failed: %s", provider_name, attempt, error)
                    if attempt <= self.settings.max_retries_per_provider:
                        self.sleep_fn(0)
        raise AllProvidersFailed(failures)

    def run_tool_loop(
        self,
        user_text: str,
        tools: list[ToolSpec],
        dispatcher: Dispatcher,
        system_prompt: str = "You are Jarvis. Use only the registered tools and be concise.",
    ) -> str:
        if not user_text.strip():
            raise ValueError("Command cannot be empty")
        if len(user_text) > self.settings.max_input_chars:
            raise ValueError("Command exceeds the configured input limit")

        messages = [ChatMessage("system", system_prompt), ChatMessage("user", user_text)]
        for _ in range(self.settings.max_tool_rounds):
            response = self.complete(messages, tools)
            if not response.tool_calls:
                return response.content.strip()

            messages.append(
                ChatMessage(
                    role="assistant",
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )
            for call in response.tool_calls:
                result = dispatcher.dispatch(call.name, call.arguments)
                messages.append(
                    ChatMessage(
                        role="tool",
                        name=call.name,
                        tool_call_id=call.id,
                        content=_serialize_result(result),
                    )
                )
        raise RuntimeError("Maximum tool-calling rounds exceeded")


def _safe_error(exc: Exception) -> str:
    """Avoid logging exception representations that may contain credentials."""
    text = str(exc).replace("\n", " ")
    for marker in ("key=", "api_key=", "Bearer "):
        if marker in text:
            text = text.split(marker, 1)[0] + marker + "[REDACTED]"
    return text[:500]


def _serialize_result(result: Any) -> str:
    if hasattr(result, "__dict__"):
        result = result.__dict__
    return str(result)


__all__ = ["AllProvidersFailed", "LLMRouter", "Provider", "RouteEvent"]
