"""Preview-first routines built only from registered safe tools."""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class WorkflowStep:
    tool_name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class WorkflowDefinition:
    workflow_id: str
    name: str
    steps: tuple[WorkflowStep, ...]
    enabled: bool
    created_at: float


class WorkflowStore:
    def __init__(self, path: Path, now: Callable[[], float] | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._now = now or time.time
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS workflows (workflow_id TEXT PRIMARY KEY, "
                "name TEXT NOT NULL, steps_json TEXT NOT NULL, "
                "enabled INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL)"
            )

    def create(self, name: str, steps: list[WorkflowStep]) -> WorkflowDefinition:
        import json

        clean_name = str(name).strip()[:120]
        if not clean_name:
            raise ValueError("Workflow name cannot be empty")
        if not 1 <= len(steps) <= 10:
            raise ValueError("Workflow must contain between 1 and 10 steps")
        for step in steps:
            if not isinstance(step.tool_name, str) or not step.tool_name.strip():
                raise ValueError("Workflow step tool name cannot be empty")
            if not isinstance(step.arguments, dict):
                raise ValueError("Workflow step arguments must be an object")
        workflow_id = f"workflow-{uuid.uuid4().hex[:16]}"
        created_at = self._now()
        definition = WorkflowDefinition(workflow_id, clean_name, tuple(steps), True, created_at)
        payload = json.dumps(
            [{"tool_name": step.tool_name, "arguments": step.arguments} for step in steps],
            separators=(",", ":"),
        )
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO workflows(workflow_id, name, steps_json, enabled, created_at) "
                "VALUES (?, ?, ?, 1, ?)",
                (workflow_id, clean_name, payload, created_at),
            )
        return definition

    def list(self) -> list[WorkflowDefinition]:
        import json

        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT * FROM workflows ORDER BY created_at DESC").fetchall()
        return [
            WorkflowDefinition(
                str(row["workflow_id"]),
                str(row["name"]),
                tuple(
                    WorkflowStep(str(item["tool_name"]), dict(item["arguments"]))
                    for item in json.loads(row["steps_json"])
                ),
                bool(row["enabled"]),
                float(row["created_at"]),
            )
            for row in rows
        ]

    def set_enabled(self, workflow_id: str, enabled: bool) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "UPDATE workflows SET enabled=? WHERE workflow_id=?",
                (int(bool(enabled)), workflow_id),
            )
        return cursor.rowcount == 1


class SafeWorkflowEngine:
    """Run only explicitly registered SAFE tools; no visual automation or raw code."""

    def __init__(self, store: WorkflowStore, registry: Any, dispatcher: Any) -> None:
        self.store = store
        self.registry = registry
        self.dispatcher = dispatcher

    def preview(self, workflow_id: str) -> list[dict[str, Any]]:
        definition = self._find(workflow_id)
        return [
            {
                "step": index,
                "tool": step.tool_name,
                "arguments": dict(step.arguments),
                "risk": "SAFE",
            }
            for index, step in enumerate(definition.steps, 1)
        ]

    def run(self, workflow_id: str) -> list[Any]:
        definition = self._find(workflow_id)
        if not definition.enabled:
            raise PermissionError("Workflow is disabled")
        results = []
        for step in definition.steps:
            tool = self.registry.get(step.tool_name)
            if tool is None:
                raise ValueError(f"Workflow tool is not registered: {step.tool_name}")
            if str(tool.risk) != "SAFE":
                raise PermissionError("Workflows can run only SAFE tools")
            result = self.dispatcher.dispatch(step.tool_name, step.arguments)
            if getattr(result, "error", None):
                raise RuntimeError(str(result.error))
            results.append(result)
        return results

    def _find(self, workflow_id: str) -> WorkflowDefinition:
        for definition in self.store.list():
            if definition.workflow_id == workflow_id:
                return definition
        raise ValueError("Workflow does not exist")


__all__ = ["SafeWorkflowEngine", "WorkflowDefinition", "WorkflowStep", "WorkflowStore"]
