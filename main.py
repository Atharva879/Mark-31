"""Command-line entry point for the local Jarvis agent."""

from __future__ import annotations

import logging

from audit import AuditLogger
from config import Settings
from dispatcher import Dispatcher, ToolRegistry
from llm.gemini_client import GeminiClient
from llm.openrouter_client import OpenRouterClient
from llm.router import AllProvidersFailed, LLMRouter
from llm.schemas import RiskTier, ToolSpec
from skills.mock_tools import echo_status, get_current_time, remember_note


def build_runtime(settings: Settings | None = None) -> tuple[LLMRouter, Dispatcher, ToolRegistry]:
    settings = settings or Settings.from_env()
    logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
    audit = AuditLogger(settings.audit_log_path)
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="get_current_time",
            description="Return the current UTC time.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            risk=RiskTier.SAFE,
            handler=get_current_time,
        )
    )
    registry.register(
        ToolSpec(
            name="echo_status",
            description="Return a status message without changing anything.",
            parameters={
                "type": "object",
                "properties": {"message": {"type": "string", "maxLength": 2_000}},
                "required": ["message"],
                "additionalProperties": False,
            },
            risk=RiskTier.SAFE,
            handler=echo_status,
        )
    )
    registry.register(
        ToolSpec(
            name="remember_note",
            description="Accept a note for the current session; durable memory is not enabled yet.",
            parameters={
                "type": "object",
                "properties": {"note": {"type": "string", "maxLength": 4_000}},
                "required": ["note"],
                "additionalProperties": False,
            },
            risk=RiskTier.SAFE,
            handler=remember_note,
        )
    )

    providers = {
        "gemini": GeminiClient(settings.gemini_api_key, settings.gemini_model, settings.request_timeout_seconds),
        "openrouter": OpenRouterClient(
            settings.openrouter_api_key,
            settings.openrouter_model,
            settings.request_timeout_seconds,
        ),
    }
    dispatcher = Dispatcher(registry, audit)
    return LLMRouter(providers, settings), dispatcher, registry


def run_cli() -> None:
    router, dispatcher, registry = build_runtime()
    print("Jarvis is ready. Type 'exit' to quit; type 'tools' to list safe tools.")
    while True:
        try:
            command = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if command.lower() in {"exit", "quit"}:
            return
        if command.lower() == "tools":
            for spec in registry.all():
                print(f"- {spec.name} [{spec.risk.value}]: {spec.description}")
            continue
        if not command:
            continue
        try:
            response = router.run_tool_loop(command, registry.all(), dispatcher)
            print(f"Jarvis> {response}")
        except AllProvidersFailed as exc:
            print(f"Jarvis provider error> {exc}")
        except Exception as exc:
            print(f"Jarvis error> {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    run_cli()
