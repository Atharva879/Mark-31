"""Persistent local scheduling for bounded monitoring triggers.

Schedules are active only while the Jarvis desktop process is alive. APScheduler
handles interval timing; SQLite remains the source of truth for definitions and
immutable-ish run history. This module contains monitoring only, not arbitrary
code or unattended state-changing actions.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from apscheduler.schedulers.background import BackgroundScheduler as APSBackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

MIN_INTERVAL_SECONDS = 60
MAX_INTERVAL_SECONDS = 7 * 24 * 60 * 60


@dataclass(frozen=True)
class Trigger:
    trigger_id: str
    name: str
    kind: str
    interval_seconds: int
    enabled: bool
    payload: dict[str, Any]
    next_run_at: float


@dataclass(frozen=True)
class TriggerRun:
    run_id: str
    trigger_id: str
    started_at: str
    finished_at: str | None
    status: str
    summary: str


class SchedulerValidationError(ValueError):
    pass


class SchedulerStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS triggers ("
                "trigger_id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, "
                "interval_seconds INTEGER NOT NULL, enabled INTEGER NOT NULL, "
                "payload_json TEXT NOT NULL, "
                "next_run_at REAL NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS trigger_runs ("
                "run_id TEXT PRIMARY KEY, trigger_id TEXT NOT NULL, started_at TEXT NOT NULL, "
                "finished_at TEXT, status TEXT NOT NULL, summary TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_trigger_runs_trigger "
                "ON trigger_runs(trigger_id, started_at DESC)"
            )

    def save_trigger(self, trigger: Trigger) -> None:
        now = _now()
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO triggers(trigger_id, name, kind, interval_seconds, enabled, "
                "payload_json, next_run_at, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(trigger_id) DO UPDATE SET name=excluded.name, "
                "kind=excluded.kind, interval_seconds=excluded.interval_seconds, "
                "enabled=excluded.enabled, payload_json=excluded.payload_json, "
                "next_run_at=excluded.next_run_at, updated_at=excluded.updated_at",
                (
                    trigger.trigger_id,
                    trigger.name,
                    trigger.kind,
                    trigger.interval_seconds,
                    int(trigger.enabled),
                    json.dumps(trigger.payload, ensure_ascii=False),
                    trigger.next_run_at,
                    now,
                    now,
                ),
            )

    def get_trigger(self, trigger_id: str) -> Trigger | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM triggers WHERE trigger_id=?", (trigger_id,)
            ).fetchone()
        return _trigger_from_row(row) if row else None

    def list_triggers(self) -> list[Trigger]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM triggers ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [_trigger_from_row(row) for row in rows]

    def delete_trigger(self, trigger_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM triggers WHERE trigger_id=?", (trigger_id,))
            return cursor.rowcount == 1

    def record_run(self, run: TriggerRun) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO trigger_runs(run_id, trigger_id, started_at, "
                "finished_at, status, summary) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run.run_id,
                    run.trigger_id,
                    run.started_at,
                    run.finished_at,
                    run.status,
                    run.summary[:4_000],
                ),
            )

    def recent_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT run_id, trigger_id, started_at, finished_at, status, summary "
                "FROM trigger_runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]


def _trigger_from_row(row: sqlite3.Row) -> Trigger:
    return Trigger(
        trigger_id=str(row["trigger_id"]),
        name=str(row["name"]),
        kind=str(row["kind"]),
        interval_seconds=int(row["interval_seconds"]),
        enabled=bool(row["enabled"]),
        payload=json.loads(row["payload_json"]),
        next_run_at=float(row["next_run_at"]),
    )


class BackgroundScheduler:
    """Persistent monitor scheduler backed by APScheduler's daemon worker."""

    def __init__(
        self,
        store: SchedulerStore,
        monitor: Callable[[Trigger], tuple[str, bool, dict[str, Any]]],
        notify: Callable[[str], None] | None = None,
        poll_seconds: float = 1.0,
        max_run_history: int = 500,
        loop_runner: Callable[[Trigger], tuple[str, bool, dict[str, Any]]] | None = None,
    ) -> None:
        del poll_seconds  # APScheduler owns timing; retained for config compatibility.
        self.store = store
        self.monitor = monitor
        self.notify = notify or (lambda _message: None)
        self.loop_runner = loop_runner
        self.max_run_history = max(50, min(int(max_run_history), 10_000))
        self._scheduler: APSBackgroundScheduler | None = None
        self._active: set[str] = set()
        self._active_lock = threading.Lock()
        self._lifecycle_lock = threading.RLock()

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._scheduler is not None and self._scheduler.running:
                return
            scheduler = APSBackgroundScheduler(
                job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 60},
                daemon=True,
            )
            self._scheduler = scheduler
            for trigger in self.store.list_triggers():
                if trigger.enabled:
                    self._add_job(trigger)
            scheduler.start()

    def stop(self, timeout: float = 2.0) -> None:
        del timeout  # shutdown(wait=False) is intentionally non-blocking for UI exit.
        with self._lifecycle_lock:
            if self._scheduler is not None and self._scheduler.running:
                self._scheduler.shutdown(wait=False)
            self._scheduler = None

    def create_trigger(
        self,
        name: str,
        kind: str,
        interval_seconds: int,
        payload: Mapping[str, Any],
        enabled: bool = True,
    ) -> dict[str, Any]:
        name = _bounded(name, "name", 120)
        kind = _bounded(kind, "kind", 40).lower()
        if kind not in {"web_url", "file", "reminder", "loop"}:
            raise SchedulerValidationError("kind must be web_url, file, reminder, or loop")
        payload = dict(payload)
        if kind == "loop":
            if self.loop_runner is None:
                raise SchedulerValidationError("loop triggers require a configured loop runner")
            if not isinstance(payload.get("loop_id"), str) or not isinstance(
                payload.get("tool"), str
            ):
                raise SchedulerValidationError("loop payload requires loop_id and tool")
        if kind == "loop":
            required_key = "tool"
            target = payload.get(required_key)
            if not isinstance(target, str) or not target.strip():
                raise SchedulerValidationError("loop payload must include a non-empty tool")
        else:
            required_key = "url" if kind == "web_url" else "path" if kind == "file" else "message"
        target = payload.get(required_key)
        if not isinstance(target, str) or not target.strip() or len(target.strip()) > 2_000:
            raise SchedulerValidationError(f"payload must include a non-empty {required_key}")
        if kind == "web_url" and not target.lower().startswith(("http://", "https://")):
            raise SchedulerValidationError("web_url monitors require an HTTP(S) URL")
        if kind == "reminder" and len(target.strip()) > 1_000:
            raise SchedulerValidationError("reminder messages must be under 1,000 characters")
        try:
            interval = int(interval_seconds)
        except (TypeError, ValueError) as exc:
            raise SchedulerValidationError("interval_seconds must be an integer") from exc
        if not MIN_INTERVAL_SECONDS <= interval <= MAX_INTERVAL_SECONDS:
            raise SchedulerValidationError(
                f"interval_seconds must be between {MIN_INTERVAL_SECONDS} and "
                f"{MAX_INTERVAL_SECONDS}"
            )
        trigger_id = uuid.uuid4().hex[:12]
        trigger = Trigger(
            trigger_id, name, kind, interval, bool(enabled), payload, time.time() + interval
        )
        self.store.save_trigger(trigger)
        if trigger.enabled:
            self._add_job(trigger)
        return _trigger_dict(trigger)

    def set_enabled(self, trigger_id: str, enabled: bool) -> dict[str, Any]:
        trigger = self._require(trigger_id)
        updated = Trigger(
            trigger.trigger_id,
            trigger.name,
            trigger.kind,
            trigger.interval_seconds,
            bool(enabled),
            trigger.payload,
            time.time() + trigger.interval_seconds,
        )
        self.store.save_trigger(updated)
        self._remove_job(trigger.trigger_id)
        if updated.enabled:
            self._add_job(updated)
        return _trigger_dict(updated)

    def delete(self, trigger_id: str) -> bool:
        trigger_id = _bounded(trigger_id, "trigger_id", 80)
        deleted = self.store.delete_trigger(trigger_id)
        if deleted:
            self._remove_job(trigger_id)
        return deleted

    def list(self) -> list[dict[str, Any]]:
        return [_trigger_dict(trigger) for trigger in self.store.list_triggers()]

    def status(self) -> dict[str, Any]:
        triggers = self.store.list_triggers()
        return {
            "running": bool(self._scheduler and self._scheduler.running),
            "enabled": sum(item.enabled for item in triggers),
            "total": len(triggers),
            "recent_runs": self.store.recent_runs(10),
        }

    def run_once(self, trigger_id: str) -> dict[str, Any]:
        trigger = self._require(trigger_id)
        return self._execute(trigger)

    def _add_job(self, trigger: Trigger) -> None:
        scheduler = self._scheduler
        if scheduler is None:
            return
        start = datetime.fromtimestamp(max(trigger.next_run_at, time.time()), UTC)
        scheduler.add_job(
            self._execute_job,
            trigger=IntervalTrigger(
                seconds=trigger.interval_seconds, start_date=start, timezone=UTC
            ),
            args=[trigger.trigger_id],
            id=trigger.trigger_id,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=60,
        )

    def _remove_job(self, trigger_id: str) -> None:
        scheduler = self._scheduler
        if scheduler is None:
            return
        try:
            scheduler.remove_job(trigger_id)
        except Exception:
            pass

    def _execute_job(self, trigger_id: str) -> None:
        trigger = self.store.get_trigger(trigger_id)
        if trigger is not None and trigger.enabled:
            self._execute(trigger)

    def _execute(self, trigger: Trigger) -> dict[str, Any]:
        with self._active_lock:
            if trigger.trigger_id in self._active:
                return {
                    "status": "skipped",
                    "reason": "already_running",
                    "trigger_id": trigger.trigger_id,
                }
            self._active.add(trigger.trigger_id)
        run_id = uuid.uuid4().hex
        started = _now()
        try:
            if trigger.kind == "loop":
                if self.loop_runner is None:
                    raise SchedulerValidationError("loop runner is unavailable")
                summary, changed, state = self.loop_runner(trigger)
            else:
                summary, changed, state = self.monitor(trigger)
            payload = dict(trigger.payload)
            payload["last_state"] = state
            payload["last_changed"] = bool(changed)
            payload["last_checked_at"] = started
            current = self.store.get_trigger(trigger.trigger_id)
            if current is None:
                status = "changed" if changed else "unchanged"
                self.store.record_run(
                    TriggerRun(run_id, trigger.trigger_id, started, _now(), status, summary)
                )
                self._trim_history()
                return {
                    "run_id": run_id,
                    "trigger_id": trigger.trigger_id,
                    "status": status,
                    "summary": summary,
                    "state": state,
                }
            updated = Trigger(
                trigger.trigger_id,
                current.name,
                current.kind,
                current.interval_seconds,
                current.enabled,
                payload,
                time.time() + current.interval_seconds,
            )
            self.store.save_trigger(updated)
            status = "changed" if changed else "unchanged"
            self.store.record_run(
                TriggerRun(run_id, trigger.trigger_id, started, _now(), status, summary)
            )
            self._trim_history()
            if changed or trigger.kind == "reminder":
                label = "reminder" if trigger.kind == "reminder" else "monitor"
                detail = "scheduled" if trigger.kind == "reminder" else "change detected"
                self.notify(f"Scheduled {label} '{trigger.name}': {detail}. {summary[:240]}")
            return {
                "run_id": run_id,
                "trigger_id": trigger.trigger_id,
                "status": status,
                "summary": summary,
                "state": state,
            }
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:500]}"
            self.store.record_run(
                TriggerRun(run_id, trigger.trigger_id, started, _now(), "failed", error)
            )
            self._trim_history()
            self.notify(f"Scheduled monitor '{trigger.name}' failed: {error}")
            return {
                "run_id": run_id,
                "trigger_id": trigger.trigger_id,
                "status": "failed",
                "error": error,
            }
        finally:
            with self._active_lock:
                self._active.discard(trigger.trigger_id)

    def _trim_history(self) -> None:
        with self.store._lock, self.store._connect() as connection:
            connection.execute(
                "DELETE FROM trigger_runs WHERE run_id NOT IN ("
                "SELECT run_id FROM trigger_runs ORDER BY started_at DESC LIMIT ?)",
                (self.max_run_history,),
            )

    def _require(self, trigger_id: str) -> Trigger:
        trigger = self.store.get_trigger(_bounded(trigger_id, "trigger_id", 80))
        if trigger is None:
            raise SchedulerValidationError("Trigger was not found")
        return trigger


def _bounded(value: str, label: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise SchedulerValidationError(
            f"{label} must be a non-empty string under {limit} characters"
        )
    return value.strip()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _trigger_dict(trigger: Trigger) -> dict[str, Any]:
    return {
        "trigger_id": trigger.trigger_id,
        "name": trigger.name,
        "kind": trigger.kind,
        "interval_seconds": trigger.interval_seconds,
        "enabled": trigger.enabled,
        "payload": trigger.payload,
        "next_run_at": trigger.next_run_at,
    }


__all__ = [
    "BackgroundScheduler",
    "MIN_INTERVAL_SECONDS",
    "MAX_INTERVAL_SECONDS",
    "SchedulerStore",
    "SchedulerValidationError",
    "Trigger",
    "TriggerRun",
]
