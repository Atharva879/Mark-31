"""Headless-safe helpers for local desktop UI configuration."""

from __future__ import annotations

import os
from pathlib import Path


def write_local_env(
    gemini_key: str,
    openrouter_key: str,
    order: str,
    gemini_model: str = "gemini-3.6-flash",
    openrouter_model: str = "deepseek/deepseek-chat-v3.1",
    path: Path | str = ".env",
) -> None:
    """Persist Gemini/OpenRouter settings without logging their values."""
    target = Path(path)
    existing: dict[str, str] = {}
    if target.exists():
        for line in target.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                existing[key.strip()] = value
    existing.pop("JARVIS_LOCAL_MODEL", None)
    existing.pop("JARVIS_LOCAL_BASE_URL", None)
    existing.update(
        {
            "GEMINI_API_KEY": gemini_key,
            "OPENROUTER_API_KEY": openrouter_key,
            "JARVIS_PROVIDER_ORDER": order,
            "GEMINI_MODEL": gemini_model,
            "OPENROUTER_MODEL": openrouter_model,
        }
    )
    target.write_text(
        "\n".join(f"{key}={value}" for key, value in existing.items()) + "\n", encoding="utf-8"
    )
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass


__all__ = ["write_local_env"]
