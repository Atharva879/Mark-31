"""Local OpenAI-compatible LLM adapter with localhost-only endpoint policy."""

from __future__ import annotations

from urllib.parse import urlparse

from .openrouter_client import OpenRouterClient


class LocalLLMClient(OpenRouterClient):
    provider_name = "local"

    def __init__(self, model: str, base_url: str, timeout_seconds: float = 30.0) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Local LLM endpoint must be an HTTP localhost URL")
        # The inherited adapter requires a non-empty token; local servers commonly
        # ignore this header, but a placeholder avoids treating local auth as absent.
        super().__init__("local", model, timeout_seconds, base_url)


__all__ = ["LocalLLMClient"]
