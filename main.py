"""Command-line entry point for the local Jarvis agent."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

from agent_orchestrator import MultiAgentCoordinator
from audit import AuditLogger
from config import Settings
from dispatcher import Dispatcher, ToolRegistry
from llm.gemini_client import GeminiClient
from llm.openrouter_client import OpenRouterClient
from llm.local_client import LocalLLMClient
from llm.router import AllProvidersFailed, LLMRouter
from llm.schemas import RiskTier, ToolSpec
from memory.long_term import LongTermMemory
from skills.apps import AppConfig, ApplicationController
from skills.browser import ReadOnlyBrowser
from skills.code_sandbox import CodeSandbox
from skills.files import ScopedFileManager
from skills.messaging_discord import DiscordClient
from skills.messaging_whatsapp import WhatsAppDesktopClient
from skills.monitoring import MonitorRegistry
from skills.mock_tools import echo_status, get_current_time
from skills.multimodal import MultimodalIngestor
from skills.shell import SafeCommandExecutor
from skills.web import WebClient
from scheduler import BackgroundScheduler, SchedulerStore


def build_runtime(
    settings: Settings | None = None,
    confirm=None,
    notify=None,
) -> tuple[LLMRouter, Dispatcher, ToolRegistry]:
    settings = settings or Settings.from_env()
    logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
    audit = AuditLogger(settings.audit_log_path)
    registry = ToolRegistry()
    memory = LongTermMemory(settings.memory_db_path, settings.vector_db_path)
    _register_core_tools(registry, memory)

    if settings.allowed_roots:
        _register_file_tools(registry, ScopedFileManager(settings.allowed_roots))

    _register_application_tools(registry, _load_applications())
    _register_discord_tools(registry)
    _register_whatsapp_tools(registry)
    _register_web_tools(registry)
    _register_multimodal_tools(registry, settings)
    _register_shell_tools(registry, settings)
    _register_browser_tools(registry)
    _register_advanced_file_tools(registry, settings)
    _register_code_sandbox_tool(registry)

    monitor_web = _build_web_client()
    monitor_files = ScopedFileManager(settings.allowed_roots) if settings.allowed_roots else None
    scheduler = BackgroundScheduler(
        SchedulerStore(settings.scheduler_db_path),
        MonitorRegistry(monitor_web, monitor_files),
        notify=notify,
        poll_seconds=float(os.environ.get("JARVIS_SCHEDULER_POLL_SECONDS", "1")),
        max_run_history=int(os.environ.get("JARVIS_SCHEDULER_MAX_RUN_HISTORY", "500")),
    )

    providers = {
        "local": LocalLLMClient(settings.local_model, settings.local_base_url, settings.request_timeout_seconds),
        "gemini": GeminiClient(settings.gemini_api_key, settings.gemini_model, settings.request_timeout_seconds),
        "openrouter": OpenRouterClient(
            settings.openrouter_api_key,
            settings.openrouter_model,
            settings.request_timeout_seconds,
        ),
    }
    router = LLMRouter(providers, settings)
    dispatcher = Dispatcher(registry, audit, confirm=confirm, notify=notify)
    coordinator = MultiAgentCoordinator(
        router,
        audit,
        max_subtasks=int(os.environ.get("JARVIS_MAX_SUBTASKS", "5")),
        max_workers=int(os.environ.get("JARVIS_MAX_AGENT_WORKERS", "3")),
        subtask_timeout_seconds=float(os.environ.get("JARVIS_AGENT_TIMEOUT_SECONDS", "45")),
        max_prompt_chars=int(os.environ.get("JARVIS_AGENT_MAX_PROMPT_CHARS", "4000")),
        max_result_chars=int(os.environ.get("JARVIS_AGENT_MAX_RESULT_CHARS", "12000")),
    )
    registry.register(
        ToolSpec(
            name="delegate_subtasks",
            description="Run bounded read-only subtasks in parallel using approved Jarvis agent roles.",
            parameters={
                "type": "object",
                "properties": {
                    "subtasks": {
                        "type": "array",
                        "maxItems": 10,
                        "items": {
                            "type": "object",
                            "properties": {
                                "task_id": {"type": "string", "maxLength": 80},
                                "role": {"type": "string", "enum": ["researcher", "memory_analyst", "file_analyst", "synthesizer"]},
                                "prompt": {"type": "string", "maxLength": 4000},
                            },
                            "required": ["role", "prompt"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["subtasks"],
                "additionalProperties": False,
            },
            risk=RiskTier.MODERATE,
            handler=lambda subtasks: coordinator.delegate(subtasks, registry.all(), dispatcher),
        )
    )
    _register_scheduler_tools(registry, scheduler)
    registry.scheduler = scheduler
    return router, dispatcher, registry


def _build_web_client() -> WebClient:
    return WebClient(
        timeout_seconds=float(os.environ.get("JARVIS_WEB_TIMEOUT_SECONDS", "15")),
        max_response_bytes=int(os.environ.get("JARVIS_WEB_MAX_RESPONSE_BYTES", "1000000")),
        max_results=int(os.environ.get("JARVIS_WEB_MAX_RESULTS", "5")),
        allowed_hosts={item.strip().lower() for item in os.environ.get("JARVIS_WEB_ALLOWED_HOSTS", "").split(",") if item.strip()},
    )


def _register_scheduler_tools(registry: ToolRegistry, scheduler: BackgroundScheduler) -> None:
    registry.register(
        ToolSpec(
            name="create_monitor_trigger",
            description="Create a persistent bounded reminder, web, or local-file monitor; the trigger is initially enabled by default.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "maxLength": 120},
                    "kind": {"type": "string", "enum": ["web_url", "file", "reminder"]},
                    "interval_seconds": {"type": "integer", "minimum": 60, "maximum": 604800},
                    "payload": {"type": "object"},
                    "enabled": {"type": "boolean"},
                },
                "required": ["name", "kind", "interval_seconds", "payload"],
                "additionalProperties": False,
            },
            risk=RiskTier.MODERATE,
            handler=lambda name, kind, interval_seconds, payload, enabled=True: scheduler.create_trigger(name, kind, interval_seconds, payload, enabled),
        )
    )
    registry.register(
        ToolSpec(
            name="list_monitor_triggers",
            description="List persistent monitoring triggers and their enabled state.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            risk=RiskTier.SAFE,
            handler=scheduler.list,
        )
    )
    registry.register(
        ToolSpec(
            name="monitor_status",
            description="Return scheduler lifecycle status and recent monitor runs.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            risk=RiskTier.SAFE,
            handler=scheduler.status,
        )
    )
    registry.register(
        ToolSpec(
            name="set_monitor_enabled",
            description="Enable or disable a persistent monitoring trigger.",
            parameters={
                "type": "object",
                "properties": {"trigger_id": {"type": "string", "maxLength": 80}, "enabled": {"type": "boolean"}},
                "required": ["trigger_id", "enabled"],
                "additionalProperties": False,
            },
            risk=RiskTier.MODERATE,
            handler=scheduler.set_enabled,
        )
    )
    registry.register(
        ToolSpec(
            name="run_monitor_now",
            description="Run one configured monitor immediately without changing local or external state.",
            parameters={"type": "object", "properties": {"trigger_id": {"type": "string", "maxLength": 80}}, "required": ["trigger_id"], "additionalProperties": False},
            risk=RiskTier.MODERATE,
            handler=scheduler.run_once,
        )
    )
    registry.register(
        ToolSpec(
            name="delete_monitor_trigger",
            description="Delete a persistent monitoring trigger and retain its historical run records.",
            parameters={"type": "object", "properties": {"trigger_id": {"type": "string", "maxLength": 80}}, "required": ["trigger_id"], "additionalProperties": False},
            risk=RiskTier.SENSITIVE,
            handler=lambda trigger_id: {"deleted": scheduler.delete(trigger_id), "trigger_id": trigger_id},
        )
    )


def _register_core_tools(registry: ToolRegistry, memory: LongTermMemory) -> None:
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
    registry.register(
        ToolSpec(
            name="semantic_recall_memory",
            description="Find bounded long-term memories by local semantic similarity.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "maxLength": 500},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    "min_score": {"type": "number"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            risk=RiskTier.SAFE,
            handler=lambda query, limit=10, min_score=0.1: memory.semantic_recall(query, limit, min_score),
        )
    )
    registry.register(
        ToolSpec(
            name="reindex_memory",
            description="Rebuild the local vector index from durable SQLite memories.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            risk=RiskTier.MODERATE,
            handler=lambda: {"indexed": memory.reindex(), "stats": memory.stats()},
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


def _register_discord_tools(registry: ToolRegistry) -> None:
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    channel_ids = [item.strip() for item in os.environ.get("DISCORD_ALLOWED_CHANNEL_IDS", "").split(",") if item.strip()]
    if not token or not channel_ids:
        return
    client = DiscordClient(token, channel_ids)
    registry.register(
        ToolSpec(
            name="send_discord_message",
            description="Send a message to an explicitly allowlisted Discord channel.",
            parameters={
                "type": "object",
                "properties": {
                    "channel_id": {"type": "string", "maxLength": 30},
                    "content": {"type": "string", "maxLength": 2_000},
                },
                "required": ["channel_id", "content"],
                "additionalProperties": False,
            },
            risk=RiskTier.MODERATE,
            handler=client.send_message,
        )
    )


def _register_advanced_file_tools(registry: ToolRegistry, settings: Settings) -> None:
    if not settings.allowed_roots:
        return
    files = ScopedFileManager(settings.allowed_roots)
    registry.register(
        ToolSpec(
            name="find_files",
            description="Recursively find files under configured roots by a bounded glob pattern.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "maxLength": 200},
                    "directory": {"type": "string", "maxLength": 2_000},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 1_000},
                },
                "additionalProperties": False,
            },
            risk=RiskTier.SAFE,
            handler=lambda query="*", directory=".", max_results=100: files.find_files(query, directory, max_results),
        )
    )
    registry.register(
        ToolSpec(
            name="file_metadata",
            description="Return metadata for an allowed local file or directory.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string", "maxLength": 2_000}},
                "required": ["path"],
                "additionalProperties": False,
            },
            risk=RiskTier.SAFE,
            handler=files.metadata,
        )
    )
    registry.register(
        ToolSpec(
            name="hash_file_sha256",
            description="Calculate a bounded SHA-256 hash for an allowed local file.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string", "maxLength": 2_000}},
                "required": ["path"],
                "additionalProperties": False,
            },
            risk=RiskTier.SAFE,
            handler=files.sha256,
        )
    )
    registry.register(
        ToolSpec(
            name="inspect_archive",
            description="List ZIP or TAR-family archive members without extracting or executing them.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "maxLength": 2_000},
                    "max_entries": {"type": "integer", "minimum": 1, "maximum": 2_000},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            risk=RiskTier.SAFE,
            handler=lambda path, max_entries=200: files.inspect_archive(path, max_entries),
        )
    )


def _register_code_sandbox_tool(registry: ToolRegistry) -> None:
    sandbox = CodeSandbox(
        timeout_seconds=float(os.environ.get("JARVIS_SANDBOX_TIMEOUT_SECONDS", "5")),
        max_output_chars=int(os.environ.get("JARVIS_SANDBOX_MAX_OUTPUT_CHARS", "12000")),
        max_code_chars=int(os.environ.get("JARVIS_SANDBOX_MAX_CODE_CHARS", "8000")),
        memory_limit_mb=int(os.environ.get("JARVIS_SANDBOX_MEMORY_LIMIT_MB", "256")),
    )
    registry.register(
        ToolSpec(
            name="run_python_sandbox",
            description="Run small pure Python calculations in an isolated temporary subprocess; confirmation is always required.",
            parameters={
                "type": "object",
                "properties": {"code": {"type": "string", "maxLength": 8_000}},
                "required": ["code"],
                "additionalProperties": False,
            },
            risk=RiskTier.SENSITIVE,
            handler=sandbox.execute,
        )
    )


def _register_shell_tools(registry: ToolRegistry, settings: Settings) -> None:
    allowlist = {
        item.strip().lower()
        for item in os.environ.get("JARVIS_SHELL_ALLOWLIST", "echo,whoami,where,ipconfig,git").split(",")
        if item.strip()
    }
    executor = SafeCommandExecutor(
        allowlist,
        settings.allowed_roots,
        timeout_seconds=float(os.environ.get("JARVIS_SHELL_TIMEOUT_SECONDS", "15")),
        max_output_chars=int(os.environ.get("JARVIS_SHELL_MAX_OUTPUT_CHARS", "12000")),
    )
    registry.register(
        ToolSpec(
            name="run_shell_command",
            description="Run one explicitly allowlisted local command without shell interpretation; confirmation is always required.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "maxLength": 2_000},
                    "working_directory": {"type": "string", "maxLength": 2_000},
                },
                "required": ["command"],
                "additionalProperties": False,
            },
            risk=RiskTier.SENSITIVE,
            handler=lambda command, working_directory=None: executor.execute(command, working_directory),
        )
    )


def _register_browser_tools(registry: ToolRegistry) -> None:
    client = WebClient(
        timeout_seconds=float(os.environ.get("JARVIS_WEB_TIMEOUT_SECONDS", "15")),
        max_response_bytes=int(os.environ.get("JARVIS_WEB_MAX_RESPONSE_BYTES", "1000000")),
        max_results=int(os.environ.get("JARVIS_WEB_MAX_RESULTS", "5")),
        allowed_hosts={item.strip().lower() for item in os.environ.get("JARVIS_WEB_ALLOWED_HOSTS", "").split(",") if item.strip()},
    )
    browser = ReadOnlyBrowser(client)
    registry.register(
        ToolSpec(
            name="browse_web_page",
            description="Read a public web page in read-only mode; never submit forms, execute scripts, or download files.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "maxLength": 2_000},
                    "max_chars": {"type": "integer", "minimum": 1, "maximum": 100_000},
                },
                "required": ["url"],
                "additionalProperties": False,
            },
            risk=RiskTier.SAFE,
            handler=lambda url, max_chars=12_000: browser.navigate(url, max_chars),
        )
    )


def _register_multimodal_tools(registry: ToolRegistry, settings: Settings) -> None:
    if not settings.allowed_roots:
        return
    max_bytes = int(os.environ.get("JARVIS_MULTIMODAL_MAX_BYTES", "12000000"))
    max_chars = int(os.environ.get("JARVIS_DOCUMENT_MAX_CHARS", "80000"))
    ingestor = MultimodalIngestor(settings.allowed_roots, max_bytes=max_bytes, max_chars=max_chars)
    registry.register(
        ToolSpec(
            name="analyze_local_document",
            description="Extract bounded text from an allowed local document and analyze it for the user.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "maxLength": 2_000},
                    "request": {"type": "string", "maxLength": 4_000},
                },
                "required": ["path", "request"],
                "additionalProperties": False,
            },
            risk=RiskTier.SAFE,
            handler=lambda path, request: {"document": ingestor.extract_document(path).__dict__, "status": "extracted_for_analysis"},
        )
    )


def _register_web_tools(registry: ToolRegistry) -> None:
    max_results = int(os.environ.get("JARVIS_WEB_MAX_RESULTS", "5"))
    max_bytes = int(os.environ.get("JARVIS_WEB_MAX_RESPONSE_BYTES", "1000000"))
    timeout = float(os.environ.get("JARVIS_WEB_TIMEOUT_SECONDS", "15"))
    allowed_hosts = {item.strip().lower() for item in os.environ.get("JARVIS_WEB_ALLOWED_HOSTS", "").split(",") if item.strip()}
    client = WebClient(timeout_seconds=timeout, max_response_bytes=max_bytes, max_results=max_results, allowed_hosts=allowed_hosts)
    registry.register(
        ToolSpec(
            name="web_search",
            description="Search public web results and return bounded titles, URLs, and snippets.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "maxLength": 500},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            risk=RiskTier.SAFE,
            handler=lambda query, max_results=None: client.search(query, max_results),
        )
    )
    registry.register(
        ToolSpec(
            name="fetch_web_data",
            description="Fetch current public text or JSON from an absolute HTTP(S) URL with SSRF protection and size limits.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "maxLength": 2_000},
                    "max_chars": {"type": "integer", "minimum": 1, "maximum": 100_000},
                },
                "required": ["url"],
                "additionalProperties": False,
            },
            risk=RiskTier.SAFE,
            handler=lambda url, max_chars=12_000: client.fetch_url(url, max_chars),
        )
    )


def _register_whatsapp_tools(registry: ToolRegistry) -> None:
    if os.environ.get("WHATSAPP_ENABLED", "false").strip().lower() not in {"1", "true", "yes", "on"}:
        return
    dry_run = os.environ.get("WHATSAPP_DRY_RUN", "true").strip().lower() not in {"0", "false", "no", "off"}
    client = WhatsAppDesktopClient(dry_run=dry_run)
    registry.register(
        ToolSpec(
            name="send_whatsapp_message",
            description="Send a WhatsApp Desktop message to a named contact; dry-run is enabled by default.",
            parameters={
                "type": "object",
                "properties": {
                    "contact": {"type": "string", "maxLength": 300},
                    "content": {"type": "string", "maxLength": 4_096},
                },
                "required": ["contact", "content"],
                "additionalProperties": False,
            },
            risk=RiskTier.MODERATE,
            handler=client.send_message,
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
            print(f"Models: local={router.settings.local_model}, gemini={router.settings.gemini_model}, openrouter={router.settings.openrouter_model}")
            print(f"Audit log: {router.settings.audit_log_path}")
            print(f"Memory database: {router.settings.memory_db_path}")
            print(f"Vector database: {router.settings.vector_db_path}")
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch the Jarvis local assistant")
    parser.add_argument("--cli", action="store_true", help="Use the terminal interface instead of the desktop UI")
    args = parser.parse_args()
    if args.cli:
        run_cli()
    else:
        from ui import run_app
        run_app()


if __name__ == "__main__":
    main()
