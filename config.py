"""Application configuration for the local Jarvis agent.

The module intentionally uses only the standard library so the safety and
routing core can be imported before optional Windows integrations are installed.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Validated runtime settings loaded from environment variables."""

    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    local_model: str = "llama3.2"
    local_base_url: str = "http://127.0.0.1:11434/v1/chat/completions"
    gemini_model: str = "gemini-2.0-flash"
    openrouter_model: str = "deepseek/deepseek-chat-v3.1:free"
    provider_order: tuple[str, ...] = ("gemini", "openrouter")
    request_timeout_seconds: float = 30.0
    max_retries_per_provider: int = 1
    max_tool_rounds: int = 5
    max_input_chars: int = 12_000
    log_level: str = "INFO"
    audit_log_path: Path = Path("logs/audit.jsonl")
    memory_db_path: Path = Path("memory/memory.db")
    vector_db_path: Path = Path("memory/memory.vectors.db")
    scheduler_db_path: Path = Path("memory/scheduler.db")
    allowed_roots: tuple[Path, ...] = field(default_factory=tuple)

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "Settings":
        env = os.environ if environ is None else environ
        order = tuple(
            item.strip().lower()
            for item in env.get("JARVIS_PROVIDER_ORDER", "gemini,openrouter").split(",")
            if item.strip()
        )
        if not order or len(set(order)) != len(order) or any(item not in {"local", "gemini", "openrouter"} for item in order):
            raise ValueError("JARVIS_PROVIDER_ORDER must contain unique values from local, gemini, and openrouter")

        timeout = _positive_float(env.get("JARVIS_REQUEST_TIMEOUT_SECONDS", "30"), "timeout")
        retries = _nonnegative_int(env.get("JARVIS_MAX_RETRIES_PER_PROVIDER", "1"), "retries")
        rounds = _positive_int(env.get("JARVIS_MAX_TOOL_ROUNDS", "5"), "tool rounds")
        max_input = _positive_int(env.get("JARVIS_MAX_INPUT_CHARS", "12000"), "input limit")

        roots_raw = env.get("JARVIS_ALLOWED_ROOTS", "")
        roots = tuple(Path(item).expanduser() for item in roots_raw.split(os.pathsep) if item.strip())

        return cls(
            gemini_api_key=env.get("GEMINI_API_KEY", "").strip(),
            openrouter_api_key=env.get("OPENROUTER_API_KEY", "").strip(),
            local_model=_model_name(env.get("JARVIS_LOCAL_MODEL", "llama3.2"), "JARVIS_LOCAL_MODEL"),
            local_base_url=_local_url(env.get("JARVIS_LOCAL_BASE_URL", "http://127.0.0.1:11434/v1/chat/completions")),
            gemini_model=_model_name(env.get("GEMINI_MODEL", "gemini-2.0-flash"), "GEMINI_MODEL"),
            openrouter_model=_model_name(
                env.get("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3.1:free"), "OPENROUTER_MODEL"
            ),
            provider_order=order,
            request_timeout_seconds=timeout,
            max_retries_per_provider=retries,
            max_tool_rounds=rounds,
            max_input_chars=max_input,
            log_level=env.get("JARVIS_LOG_LEVEL", "INFO").strip().upper(),
            audit_log_path=Path(env.get("JARVIS_AUDIT_LOG", "logs/audit.jsonl")).expanduser(),
            memory_db_path=Path(env.get("JARVIS_MEMORY_DB", "memory/memory.db")).expanduser(),
            vector_db_path=Path(env.get("JARVIS_VECTOR_DB", "memory/memory.vectors.db")).expanduser(),
            scheduler_db_path=Path(env.get("JARVIS_SCHEDULER_DB", "memory/scheduler.db")).expanduser(),
            allowed_roots=roots,
        )


def _model_name(value: str, label: str) -> str:
    value = value.strip()
    if not value or len(value) > 200 or not re.fullmatch(r"[A-Za-z0-9._:/-]+", value):
        raise ValueError(f"{label} must be a safe model identifier")
    return value


def _local_url(value: str) -> str:
    from urllib.parse import urlparse
    parsed = urlparse(value.strip())
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("JARVIS_LOCAL_BASE_URL must be an HTTP localhost endpoint")
    if not parsed.path.endswith("/chat/completions"):
        raise ValueError("JARVIS_LOCAL_BASE_URL must target an OpenAI-compatible chat completions endpoint")
    return parsed.geturl()


def _positive_float(value: str, label: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if parsed <= 0:
        raise ValueError(f"{label} must be greater than zero")
    return parsed


def _positive_int(value: str, label: str) -> int:
    parsed = _nonnegative_int(value, label)
    if parsed <= 0:
        raise ValueError(f"{label} must be greater than zero")
    return parsed


def _nonnegative_int(value: str, label: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an integer") from exc
    if parsed < 0:
        raise ValueError(f"{label} cannot be negative")
    return parsed


__all__ = ["Settings"]
