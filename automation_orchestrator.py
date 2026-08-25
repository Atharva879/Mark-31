"""Automation-first orchestration for explicitly approved Windows applications."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AppGrant:
    app_id: str
    process_name: str
    actions: frozenset[str]
    unattended: bool = False


class AutomationOrchestrator:
    """Routes app actions only through registered adapters and a user-approved grant."""

    def __init__(self, adapters: dict[str, Any], max_actions: int = 50, max_seconds: float = 900):
        self.adapters = dict(adapters)
        self.max_actions = max(1, min(int(max_actions), 500))
        self.max_seconds = max(5.0, min(float(max_seconds), 3600.0))
        self._grants: dict[str, AppGrant] = {}
        self._stop = threading.Event()
        self._lock = threading.RLock()

    def grant(
        self, app_id: str, process_name: str, actions: set[str], unattended: bool = False
    ) -> dict[str, object]:
        app_id = self._text(app_id, 80)
        process_name = self._text(process_name, 120)
        if app_id not in self.adapters:
            raise ValueError("application has no registered adapter")
        if not actions or any(not self._text(action, 40) for action in actions):
            raise ValueError("at least one valid action is required")
        grant = AppGrant(app_id, process_name, frozenset(actions), bool(unattended))
        with self._lock:
            self._grants[app_id] = grant
        return {
            "app_id": app_id,
            "process_name": process_name,
            "actions": sorted(actions),
            "unattended": bool(unattended),
        }

    def revoke(self, app_id: str) -> bool:
        with self._lock:
            return self._grants.pop(str(app_id), None) is not None

    def list_grants(self) -> list[dict[str, object]]:
        with self._lock:
            return [
                {
                    "app_id": g.app_id,
                    "process_name": g.process_name,
                    "actions": sorted(g.actions),
                    "unattended": g.unattended,
                }
                for g in self._grants.values()
            ]

    def stop_all(self) -> None:
        self._stop.set()

    def arm(self) -> None:
        self._stop.clear()

    def run(self, app_id: str, actions: list[dict[str, Any]]) -> dict[str, object]:
        with self._lock:
            grant = self._grants.get(str(app_id))
        if grant is None:
            raise PermissionError("application has not been explicitly granted")
        if not isinstance(actions, list) or not actions or len(actions) > self.max_actions:
            raise ValueError("actions must be a non-empty bounded list")
        adapter = self.adapters[grant.app_id]
        started = time.monotonic()
        completed = 0
        for item in actions:
            if self._stop.is_set() or time.monotonic() - started >= self.max_seconds:
                break
            if not isinstance(item, dict) or not isinstance(item.get("action"), str):
                raise ValueError("each action requires an action name")
            action = item["action"]
            if action not in grant.actions or action.startswith("_"):
                raise PermissionError(f"action is not granted: {action}")
            handler = getattr(adapter, action, None)
            if not callable(handler):
                raise ValueError(f"adapter does not expose action: {action}")
            arguments = item.get("arguments", {})
            if not isinstance(arguments, dict):
                raise ValueError("action arguments must be an object")
            handler(**arguments)
            completed += 1
        return {"app_id": grant.app_id, "completed": completed, "stopped": self._stop.is_set()}

    @staticmethod
    def _text(value: str, limit: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
            raise ValueError("text value is invalid or too long")
        return value.strip()


__all__ = ["AppGrant", "AutomationOrchestrator"]
