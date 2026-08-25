from __future__ import annotations

import importlib

from config import Settings


def test_retired_provider_models_are_normalized():
    settings = Settings.from_env(
        {
            "GEMINI_MODEL": "gemini-2.0-flash",
            "OPENROUTER_MODEL": "deepseek/deepseek-chat-v3.1:free",
            "JARVIS_PROVIDER_ORDER": "gemini,openrouter",
        }
    )
    assert settings.gemini_model == "gemini-3.6-flash"
    assert settings.openrouter_model == "deepseek/deepseek-chat-v3.1"


def test_stdlib_secrets_is_not_shadowed_by_application_module():
    stdlib_secrets = importlib.import_module("secrets")
    assert callable(stdlib_secrets.token_hex)
