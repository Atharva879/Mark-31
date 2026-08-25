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
from llm.router import AllProvidersFailed, LLMRouter
from knowledge import KnowledgeStore
from plugins import PluginCatalog
from llm.schemas import RiskTier, ToolSpec
from memory.long_term import LongTermMemory
from skills.apps import AppConfig, ApplicationController
from skills.window_manager import WindowManager
from skills.browser import ReadOnlyBrowser
from skills.code_sandbox import CodeSandbox
from skills.files import ScopedFileManager
from skills.messaging_discord import DiscordClient
from skills.messaging_whatsapp import WhatsAppDesktopClient
from skills.monitoring import MonitorRegistry
from skills.personal import ICalendarReader, PersonalStore
from skills.mock_tools import echo_status, get_current_time
from skills.multimodal import MultimodalIngestor
from skills.shell import SafeCommandExecutor
from skills.web import WebClient
from backup import BackupManager
from scheduler import BackgroundScheduler, SchedulerStore
from jarvis_secrets import SecretStore
from workflows import SafeWorkflowEngine, WorkflowStep, WorkflowStore
from task_loops import AutonomousLoopController, TaskLoopStore
from startup import StartupManager
from system_controls import SystemController
from media_publish import MediaPublisher
from automation_orchestrator import AutomationOrchestrator


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
    personal_store = PersonalStore(Path(os.environ.get("JARVIS_PERSONAL_DB", "memory/personal.db")))
    calendar_path = _configured_calendar_path(settings)
    _register_personal_tools(registry, personal_store, ICalendarReader(calendar_path))

    workflow_store = WorkflowStore(
        Path(os.environ.get("JARVIS_WORKFLOW_DB", "memory/workflows.db"))
    )
    startup_manager = StartupManager(Path(__file__).resolve())
    data_root = Path(os.environ.get("JARVIS_DATA_ROOT", "memory"))
    secret_store = SecretStore(data_root / "secrets.dpapi")
    backup_manager = BackupManager(data_root)
    knowledge_store = KnowledgeStore(
        Path(os.environ.get("JARVIS_KNOWLEDGE_DB", "memory/knowledge.db")),
        settings.allowed_roots,
    )
    system_controller = SystemController(allowed_roots=settings.allowed_roots)
    window_manager = WindowManager()
    automation_orchestrator = AutomationOrchestrator({"windows": window_manager})
    media_publisher = MediaPublisher(settings.allowed_roots)
    plugin_catalog = PluginCatalog(Path(os.environ.get("JARVIS_PLUGIN_DIR", "memory/plugins")))

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
        "gemini": GeminiClient(
            settings.gemini_api_key, settings.gemini_model, settings.request_timeout_seconds
        ),
        "openrouter": OpenRouterClient(
            settings.openrouter_api_key,
            settings.openrouter_model,
            settings.request_timeout_seconds,
        ),
    }
    router = LLMRouter(providers, settings)
    dispatcher = Dispatcher(registry, audit, confirm=confirm, notify=notify)
    loop_controller = AutonomousLoopController(
        TaskLoopStore(Path(os.environ.get("JARVIS_LOOP_DB", "memory/task_loops.db"))), dispatcher
    )
    scheduler.loop_runner = lambda trigger: _run_loop_trigger(trigger, loop_controller, registry)
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
                                "role": {
                                    "type": "string",
                                    "enum": [
                                        "researcher",
                                        "memory_analyst",
                                        "file_analyst",
                                        "synthesizer",
                                    ],
                                },
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
    workflow_engine = SafeWorkflowEngine(workflow_store, registry, dispatcher)
    _register_workflow_tools(registry, workflow_store, workflow_engine)
    registry.scheduler = scheduler
    registry.workflow_engine = workflow_engine
    _register_startup_tools(registry, startup_manager)
    registry.startup_manager = startup_manager
    registry.secret_store = secret_store
    registry.backup_manager = backup_manager
    registry.knowledge_store = knowledge_store
    registry.plugin_catalog = plugin_catalog
    registry.system_controller = system_controller
    registry.window_manager = window_manager
    registry.automation_orchestrator = automation_orchestrator
    registry.media_publisher = media_publisher
    registry.loop_controller = loop_controller
    _register_knowledge_tools(registry, knowledge_store)
    _register_system_tools(registry, system_controller)
    _register_window_tools(registry, window_manager)
    _register_media_tools(registry, media_publisher)
    return router, dispatcher, registry


def _build_web_client() -> WebClient:
    return WebClient(
        timeout_seconds=float(os.environ.get("JARVIS_WEB_TIMEOUT_SECONDS", "15")),
        max_response_bytes=int(os.environ.get("JARVIS_WEB_MAX_RESPONSE_BYTES", "1000000")),
        max_results=int(os.environ.get("JARVIS_WEB_MAX_RESULTS", "5")),
        allowed_hosts={
            item.strip().lower()
            for item in os.environ.get("JARVIS_WEB_ALLOWED_HOSTS", "").split(",")
            if item.strip()
        },
    )


def _configured_calendar_path(settings: Settings) -> Path | None:
    raw_path = os.environ.get("JARVIS_CALENDAR_ICS", "").strip()
    if not raw_path:
        return None
    candidate = Path(raw_path).expanduser().resolve()
    if not settings.allowed_roots:
        return None
    if not any(candidate == root or root in candidate.parents for root in settings.allowed_roots):
        return None
    return candidate


def _register_personal_tools(
    registry: ToolRegistry, store: PersonalStore, calendar: ICalendarReader
) -> None:
    registry.register(
        ToolSpec(
            name="create_task",
            description="Create a local task. This never contacts an external task service.",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "maxLength": 200},
                    "notes": {"type": "string", "maxLength": 2000},
                    "due_at": {"type": ["string", "null"], "maxLength": 80},
                },
                "required": ["title"],
                "additionalProperties": False,
            },
            risk=RiskTier.MODERATE,
            handler=lambda title, notes="", due_at=None: store.create_task(title, notes, due_at),
        )
    )
    registry.register(
        ToolSpec(
            name="list_tasks",
            description="List local incomplete or completed tasks.",
            parameters={
                "type": "object",
                "properties": {
                    "include_completed": {"type": "boolean"},
                    "limit": {"type": "integer", "maximum": 100},
                },
                "additionalProperties": False,
            },
            risk=RiskTier.SAFE,
            handler=lambda include_completed=False, limit=100: store.list_tasks(
                include_completed, limit
            ),
        )
    )
    registry.register(
        ToolSpec(
            name="complete_task",
            description="Mark one local task complete.",
            parameters={
                "type": "object",
                "properties": {"task_id": {"type": "integer", "minimum": 1}},
                "required": ["task_id"],
                "additionalProperties": False,
            },
            risk=RiskTier.MODERATE,
            handler=store.complete_task,
        )
    )
    registry.register(
        ToolSpec(
            name="list_calendar_events",
            description="Read bounded events from the explicitly configured local iCalendar file.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            risk=RiskTier.SAFE,
            handler=calendar.list_events,
        )
    )
    registry.register(
        ToolSpec(
            name="create_email_draft",
            description="Save a local email draft; this tool never sends email or contacts an account.",
            parameters={
                "type": "object",
                "properties": {
                    "recipient": {"type": "string", "maxLength": 320},
                    "subject": {"type": "string", "maxLength": 200},
                    "body": {"type": "string", "maxLength": 20000},
                },
                "required": ["recipient", "subject", "body"],
                "additionalProperties": False,
            },
            risk=RiskTier.MODERATE,
            handler=store.create_email_draft,
        )
    )
    registry.register(
        ToolSpec(
            name="list_email_drafts",
            description="List local email drafts without sending them.",
            parameters={
                "type": "object",
                "properties": {"limit": {"type": "integer", "maximum": 50}},
                "additionalProperties": False,
            },
            risk=RiskTier.SAFE,
            handler=store.list_email_drafts,
        )
    )


def _run_loop_trigger(trigger, controller, registry):
    payload = trigger.payload
    tool = str(payload.get("tool", ""))
    spec = registry.get(tool)
    result = controller.run(
        str(payload.get("loop_id", trigger.trigger_id)),
        tool,
        dict(payload.get("arguments", {})),
        spec.risk.value,
        int(payload.get("iterations", 1)),
    )
    completed = int(result.get("completed", 0))
    return f"Autonomous loop completed {completed} iteration(s)", completed > 0, result


def _register_media_tools(registry: ToolRegistry, publisher: MediaPublisher) -> None:
    registry.register(
        ToolSpec(
            name="find_latest_video",
            description="Find the newest supported video in an allowed local folder.",
            parameters={
                "type": "object",
                "properties": {"folder": {"type": "string", "maxLength": 400}},
                "required": ["folder"],
                "additionalProperties": False,
            },
            risk=RiskTier.SAFE,
            handler=publisher.latest_video,
        )
    )
    registry.register(
        ToolSpec(
            name="prepare_video_publish",
            description="Prepare a YouTube or Instagram publish plan from an allowed local video; does not publish.",
            parameters={
                "type": "object",
                "properties": {
                    "provider": {"type": "string", "enum": ["youtube", "instagram"]},
                    "asset_path": {"type": "string", "maxLength": 500},
                    "title": {"type": "string", "maxLength": 200},
                    "description": {"type": "string", "maxLength": 5000},
                },
                "required": ["provider", "asset_path", "title"],
                "additionalProperties": False,
            },
            risk=RiskTier.MODERATE,
            handler=publisher.prepare,
        )
    )


def _register_window_tools(registry: ToolRegistry, manager: WindowManager) -> None:
    for name, description, handler in (
        (
            "list_open_windows",
            "List visible open Windows application windows and stable handles.",
            manager.list_windows,
        ),
        ("focus_window", "Focus and restore an identified open window.", manager.focus),
        ("minimize_window", "Minimize an identified open window.", manager.minimize),
        ("maximize_window", "Maximize an identified open window.", manager.maximize),
        ("restore_window", "Restore an identified open window.", manager.restore),
        ("close_window", "Close an identified open window after confirmation.", manager.close),
    ):
        registry.register(
            ToolSpec(
                name=name,
                description=description,
                parameters={
                    "type": "object",
                    "properties": {"handle": {"type": "integer", "minimum": 1}},
                    "required": ["handle"],
                    "additionalProperties": False,
                },
                risk=RiskTier.SENSITIVE if name == "close_window" else RiskTier.MODERATE,
                confirmation_required=name == "close_window",
                handler=handler,
            )
        )
    registry.register(
        ToolSpec(
            name="move_resize_window",
            description="Move and resize an identified window inside bounded screen coordinates.",
            parameters={
                "type": "object",
                "properties": {
                    "handle": {"type": "integer", "minimum": 1},
                    "x": {"type": "integer", "minimum": 0, "maximum": 10000},
                    "y": {"type": "integer", "minimum": 0, "maximum": 10000},
                    "width": {"type": "integer", "minimum": 200, "maximum": 10000},
                    "height": {"type": "integer", "minimum": 150, "maximum": 10000},
                },
                "required": ["handle", "x", "y", "width", "height"],
                "additionalProperties": False,
            },
            risk=RiskTier.MODERATE,
            handler=manager.move_resize,
        )
    )


def _register_system_tools(registry: ToolRegistry, controller: SystemController) -> None:
    definitions = [
        (
            "system_screenshot",
            "Save a screenshot under an allowed root.",
            {"destination": {"type": "string", "maxLength": 400}},
            ["destination"],
            controller.screenshot,
        ),
        (
            "set_wifi",
            "Turn Wi-Fi on or off.",
            {"enabled": {"type": "boolean"}},
            ["enabled"],
            controller.set_wifi,
        ),
        (
            "set_bluetooth",
            "Turn Bluetooth on or off.",
            {"enabled": {"type": "boolean"}},
            ["enabled"],
            controller.set_bluetooth,
        ),
        (
            "set_volume",
            "Set system volume between 0 and 100 percent.",
            {"percent": {"type": "integer", "minimum": 0, "maximum": 100}},
            ["percent"],
            controller.set_volume,
        ),
        (
            "set_brightness",
            "Set display brightness between 0 and 100 percent.",
            {"percent": {"type": "integer", "minimum": 0, "maximum": 100}},
            ["percent"],
            controller.set_brightness,
        ),
    ]
    for name, description, properties, required, handler in definitions:
        registry.register(
            ToolSpec(
                name=name,
                description=description,
                parameters={
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
                risk=RiskTier.SENSITIVE,
                confirmation_required=True,
                handler=handler,
            )
        )


def _register_knowledge_tools(registry: ToolRegistry, store: KnowledgeStore) -> None:
    registry.register(
        ToolSpec(
            name="import_knowledge_source",
            description="Explicitly import one supported local text source under an allowed root.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string", "maxLength": 400}},
                "required": ["path"],
                "additionalProperties": False,
            },
            risk=RiskTier.MODERATE,
            handler=store.import_source,
        )
    )
    registry.register(
        ToolSpec(
            name="search_knowledge",
            description="Search explicitly imported local knowledge and return provenance citations.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "maxLength": 200},
                    "limit": {"type": "integer", "maximum": 25},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            risk=RiskTier.SAFE,
            handler=lambda query, limit=10: store.search(query, limit),
        )
    )
    registry.register(
        ToolSpec(
            name="list_knowledge_sources",
            description="List explicitly imported local knowledge sources and their checksums.",
            parameters={
                "type": "object",
                "properties": {"limit": {"type": "integer", "maximum": 100}},
                "additionalProperties": False,
            },
            risk=RiskTier.SAFE,
            handler=lambda limit=100: store.list_sources(limit),
        )
    )
    registry.register(
        ToolSpec(
            name="delete_knowledge_source",
            description="Delete one imported knowledge source from the local index.",
            parameters={
                "type": "object",
                "properties": {"source_id": {"type": "string", "maxLength": 80}},
                "required": ["source_id"],
                "additionalProperties": False,
            },
            risk=RiskTier.SENSITIVE,
            confirmation_required=True,
            handler=store.delete,
        )
    )


def _register_startup_tools(registry: ToolRegistry, manager: StartupManager) -> None:
    registry.register(
        ToolSpec(
            name="startup_status",
            description="Return whether the optional Windows startup launcher is enabled.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            risk=RiskTier.SAFE,
            handler=manager.status,
        )
    )
    registry.register(
        ToolSpec(
            name="enable_startup",
            description="Enable the per-user Windows startup launcher for Mark-31.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            risk=RiskTier.SENSITIVE,
            confirmation_required=True,
            handler=manager.enable,
        )
    )
    registry.register(
        ToolSpec(
            name="disable_startup",
            description="Disable the per-user Windows startup launcher for Mark-31.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            risk=RiskTier.SENSITIVE,
            confirmation_required=True,
            handler=manager.disable,
        )
    )


def _register_workflow_tools(
    registry: ToolRegistry, store: WorkflowStore, engine: SafeWorkflowEngine
) -> None:
    registry.register(
        ToolSpec(
            name="create_safe_workflow",
            description="Create a bounded routine from registered SAFE tools only.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "maxLength": 120},
                    "steps": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 10,
                        "items": {
                            "type": "object",
                            "properties": {
                                "tool_name": {"type": "string", "maxLength": 100},
                                "arguments": {"type": "object"},
                            },
                            "required": ["tool_name", "arguments"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["name", "steps"],
                "additionalProperties": False,
            },
            risk=RiskTier.MODERATE,
            handler=lambda name, steps: store.create(
                name, [WorkflowStep(item["tool_name"], item["arguments"]) for item in steps]
            ),
        )
    )
    registry.register(
        ToolSpec(
            name="list_safe_workflows",
            description="List saved safe workflows without executing them.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            risk=RiskTier.SAFE,
            handler=store.list,
        )
    )
    registry.register(
        ToolSpec(
            name="preview_safe_workflow",
            description="Preview the registered safe steps of a workflow without executing them.",
            parameters={
                "type": "object",
                "properties": {"workflow_id": {"type": "string", "maxLength": 80}},
                "required": ["workflow_id"],
                "additionalProperties": False,
            },
            risk=RiskTier.SAFE,
            handler=engine.preview,
        )
    )
    registry.register(
        ToolSpec(
            name="run_safe_workflow",
            description="Run a saved workflow containing SAFE registered tools only.",
            parameters={
                "type": "object",
                "properties": {"workflow_id": {"type": "string", "maxLength": 80}},
                "required": ["workflow_id"],
                "additionalProperties": False,
            },
            risk=RiskTier.MODERATE,
            handler=engine.run,
        )
    )
    registry.register(
        ToolSpec(
            name="set_safe_workflow_enabled",
            description="Enable or disable a saved safe workflow.",
            parameters={
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "maxLength": 80},
                    "enabled": {"type": "boolean"},
                },
                "required": ["workflow_id", "enabled"],
                "additionalProperties": False,
            },
            risk=RiskTier.MODERATE,
            handler=store.set_enabled,
        )
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
            handler=lambda name, kind, interval_seconds, payload, enabled=True: (
                scheduler.create_trigger(name, kind, interval_seconds, payload, enabled)
            ),
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
                "properties": {
                    "trigger_id": {"type": "string", "maxLength": 80},
                    "enabled": {"type": "boolean"},
                },
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
            parameters={
                "type": "object",
                "properties": {"trigger_id": {"type": "string", "maxLength": 80}},
                "required": ["trigger_id"],
                "additionalProperties": False,
            },
            risk=RiskTier.MODERATE,
            handler=scheduler.run_once,
        )
    )
    registry.register(
        ToolSpec(
            name="delete_monitor_trigger",
            description="Delete a persistent monitoring trigger and retain its historical run records.",
            parameters={
                "type": "object",
                "properties": {"trigger_id": {"type": "string", "maxLength": 80}},
                "required": ["trigger_id"],
                "additionalProperties": False,
            },
            risk=RiskTier.SENSITIVE,
            handler=lambda trigger_id: {
                "deleted": scheduler.delete(trigger_id),
                "trigger_id": trigger_id,
            },
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
            handler=lambda query, limit=10, min_score=0.1: memory.semantic_recall(
                query, limit, min_score
            ),
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
            handler=lambda path, content, overwrite=False: files.write_text(
                path, content, overwrite
            ),
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
    channel_ids = [
        item.strip()
        for item in os.environ.get("DISCORD_ALLOWED_CHANNEL_IDS", "").split(",")
        if item.strip()
    ]
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
            handler=lambda query="*", directory=".", max_results=100: files.find_files(
                query, directory, max_results
            ),
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
        for item in os.environ.get(
            "JARVIS_SHELL_ALLOWLIST", "echo,whoami,where,ipconfig,git"
        ).split(",")
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
            handler=lambda command, working_directory=None: executor.execute(
                command, working_directory
            ),
        )
    )


def _register_browser_tools(registry: ToolRegistry) -> None:
    client = WebClient(
        timeout_seconds=float(os.environ.get("JARVIS_WEB_TIMEOUT_SECONDS", "15")),
        max_response_bytes=int(os.environ.get("JARVIS_WEB_MAX_RESPONSE_BYTES", "1000000")),
        max_results=int(os.environ.get("JARVIS_WEB_MAX_RESULTS", "5")),
        allowed_hosts={
            item.strip().lower()
            for item in os.environ.get("JARVIS_WEB_ALLOWED_HOSTS", "").split(",")
            if item.strip()
        },
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
            handler=lambda path, request: {
                "document": ingestor.extract_document(path).__dict__,
                "status": "extracted_for_analysis",
            },
        )
    )


def _register_web_tools(registry: ToolRegistry) -> None:
    max_results = int(os.environ.get("JARVIS_WEB_MAX_RESULTS", "5"))
    max_bytes = int(os.environ.get("JARVIS_WEB_MAX_RESPONSE_BYTES", "1000000"))
    timeout = float(os.environ.get("JARVIS_WEB_TIMEOUT_SECONDS", "15"))
    allowed_hosts = {
        item.strip().lower()
        for item in os.environ.get("JARVIS_WEB_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    }
    client = WebClient(
        timeout_seconds=timeout,
        max_response_bytes=max_bytes,
        max_results=max_results,
        allowed_hosts=allowed_hosts,
    )
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
    if os.environ.get("WHATSAPP_ENABLED", "false").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return
    dry_run = os.environ.get("WHATSAPP_DRY_RUN", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
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
            str(name): AppConfig(
                str(name), Path(data["executable"]), tuple(data.get("arguments", []))
            )
            for name, data in entries.items()
        }
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "JARVIS_APP_ALLOWLIST must be a JSON object of app configurations"
        ) from exc
    return ApplicationController(applications)


def run_cli() -> None:
    router, dispatcher, registry = build_runtime()
    print(
        "Jarvis is ready. Type 'exit' to quit; type 'tools' to list tools; type 'diagnostics' for checks."
    )
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
            print(
                f"Models: local={router.settings.local_model}, gemini={router.settings.gemini_model}, openrouter={router.settings.openrouter_model}"
            )
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
    parser.add_argument(
        "--cli", action="store_true", help="Use the terminal interface instead of the desktop UI"
    )
    args = parser.parse_args()
    if args.cli:
        run_cli()
    else:
        from ui import run_app

        run_app()


if __name__ == "__main__":
    main()
