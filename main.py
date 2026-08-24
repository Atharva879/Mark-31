"""Command-line entry point for the local Jarvis agent."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from audit import AuditLogger
from config import Settings
from dispatcher import Dispatcher, ToolRegistry
from llm.gemini_client import GeminiClient
from llm.openrouter_client import OpenRouterClient
from llm.router import AllProvidersFailed, LLMRouter
from llm.schemas import RiskTier, ToolSpec
from memory.store import MemoryStore
from skills.apps import AppConfig, ApplicationController
from skills.files import ScopedFileManager
from skills.mock_tools import echo_status, get_current_time


def build_runtime(settings: Settings | None = None) -> tuple[LLMRouter, Dispatcher, ToolRegistry]:
    settings = settings or Settings.from_env()
    logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
    audit = AuditLogger(settings.audit_log_path)
    registry = ToolRegistry()
    memory = MemoryStore(settings.memory_db_path)
    _register_core_tools(registry, memory)

    if settings.allowed_roots:
        _register_file_tools(registry, ScopedFileManager(settings.allowed_roots))

    _register_application_tools(registry, _load_applications())

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


def _register_core_tools(registry: ToolRegistry, memory: MemoryStore) -> None:
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
            description="Persist an explicit user note in the local SQLite memory store.",
            parameters={
                "type": "object",
                "properties": {
                    "note": {"type": "string", "maxLength": 8_000},
                    "tags": {"type": "string", "maxLength": 500},
                },
                "required": ["note"],
                "additionalProperties": False,
            },
            risk=RiskTier.MODERATE,
            handler=lambda note, tags="": {
                "memory_id": memory.remember_note(note, tags=tags),
                "status": "saved",
            },
        )
    )
    registry.register(
        ToolSpec(
            name="recall_memory",
            description="Recall bounded local memories matching a query.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "maxLength": 500},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            risk=RiskTier.SAFE,
            handler=lambda query, limit=10: memory.recall(query, limit),
        )
    )
    registry.register(
        ToolSpec(
            name="forget_memory",
            description="Forget one local memory by its numeric ID.",
            parameters={
                "type": "object",
                "properties": {"memory_id": {"type": "integer"}},
                "required": ["memory_id"],
                "additionalProperties": False,
            },
            risk=RiskTier.SENSITIVE,
            handler=lambda memory_id: {"deleted": memory.forget(memory_id), "memory_id": memory_id},
        )
    )


def _register_file_tools(registry: ToolRegistry, files: ScopedFileManager) -> None:
    registry.register(
        ToolSpec(
            name="list_files",
            description="List files under the configured allowed roots.",
            parameters={
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "maxLength": 1_000},
                    "pattern": {"type": "string", "maxLength": 200},
                },
                "additionalProperties": False,
            },
            risk=RiskTier.SAFE,
            handler=lambda directory=".", pattern="*": files.list_files(directory, pattern),
        )
    )
    registry.register(
        ToolSpec(
            name="read_text_file",
            description="Read a UTF-8 text file under the configured allowed roots.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string", "maxLength": 1_000}},
                "required": ["path"],
                "additionalProperties": False,
            },
            risk=RiskTier.SAFE,
            handler=files.read_text,
        )
    )
    registry.register(
        ToolSpec(
            name="write_text_file",
            description="Create or overwrite a text file under the configured roots.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "maxLength": 1_000},
                    "content": {"type": "string", "maxLength": 1_000_000},
                    "overwrite": {"type": "boolean"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            risk=RiskTier.MODERATE,
            handler=lambda path, content, overwrite=False: files.write_text(path, content, overwrite),
        )
    )
    registry.register(
        ToolSpec(
            name="move_file",
            description="Move a file between configured roots.",
            parameters={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "maxLength": 1_000},
                    "destination": {"type": "string", "maxLength": 1_000},
                },
                "required": ["source", "destination"],
                "additionalProperties": False,
            },
            risk=RiskTier.MODERATE,
            handler=files.move,
        )
    )
    registry.register(
        ToolSpec(
            name="recycle_file",
            description="Move a file to the operating system Recycle Bin; never permanently delete it.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string", "maxLength": 1_000}},
                "required": ["path"],
                "additionalProperties": False,
            },
            risk=RiskTier.SENSITIVE,
            handler=files.recycle,
        )
    )


def _register_application_tools(registry: ToolRegistry, controller: ApplicationController) -> None:
    registry.register(
        ToolSpec(
            name="open_application",
            description="Open a configured allowlisted Windows application.",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string", "maxLength": 200}},
                "required": ["name"],
                "additionalProperties": False,
            },
            risk=RiskTier.SAFE,
            handler=controller.open,
        )
    )
    registry.register(
        ToolSpec(
            name="close_application",
            description="Request closure of a configured allowlisted Windows application.",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string", "maxLength": 200}},
                "required": ["name"],
                "additionalProperties": False,
            },
            risk=RiskTier.MODERATE,
            handler=controller.close,
        )
    )


def _load_applications() -> ApplicationController:
    raw = os.environ.get("JARVIS_APP_ALLOWLIST", "")
    if not raw:
        return ApplicationController()
    try:
        entries = json.loads(raw)
        applications = {
            str(name): AppConfig(str(name), Path(data["executable"]), tuple(data.get("arguments", [])))
            for name, data in entries.items()
        }
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("JARVIS_APP_ALLOWLIST must be a JSON object of app configurations") from exc
    return ApplicationController(applications)


def run_cli() -> None:
    router, dispatcher, registry = build_runtime()
    print("Jarvis is ready. Type 'exit' to quit; type 'tools' to list tools; type 'diagnostics' for checks.")
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
        if command.lower() == "diagnostics":
            print(f"Registered tools: {len(registry.all())}")
            print(f"Providers: {', '.join(router.settings.provider_order)}")
            print(f"Audit log: {router.settings.audit_log_path}")
            print(f"Memory database: {router.settings.memory_db_path}")
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
