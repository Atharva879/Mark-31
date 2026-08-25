"""Bounded autonomous task loops for pre-approved, non-sensitive tools."""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from pathlib import Path


class TaskLoopStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS loops ("
                "id TEXT PRIMARY KEY, name TEXT, tool TEXT, args TEXT, interval REAL, "
                "enabled INTEGER, runs INTEGER, last_error TEXT)"
            )

    def _connect(self):
        return sqlite3.connect(self.path)

    def create(self, name: str, tool: str, args: str, interval: float) -> str:
        loop_id = uuid.uuid4().hex[:16]
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO loops VALUES(?,?,?,?,?,?,?,?)",
                (
                    loop_id,
                    name[:120],
                    tool[:100],
                    args[:4000],
                    max(60.0, min(float(interval), 604800.0)),
                    1,
                    0,
                    "",
                ),
            )
        return loop_id

    def list(self):
        with self._lock, self._connect() as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute("SELECT * FROM loops ORDER BY name").fetchall()]

    def set_enabled(self, loop_id: str, enabled: bool) -> None:
        with self._lock, self._connect() as db:
            db.execute("UPDATE loops SET enabled=? WHERE id=?", (int(enabled), loop_id))

    def record(self, loop_id: str, error: str = "") -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE loops SET runs=runs+1,last_error=? WHERE id=?", (error[:500], loop_id)
            )


class AutonomousLoopController:
    def __init__(
        self, store: TaskLoopStore, dispatcher, max_iterations: int = 20, max_seconds: float = 300.0
    ) -> None:
        self.store = store
        self.dispatcher = dispatcher
        self.max_iterations = max(1, min(int(max_iterations), 100))
        self.max_seconds = max(5.0, min(float(max_seconds), 1800.0))
        self._stop = threading.Event()
        self._pause = threading.Event()

    def pause(self) -> None:
        self._pause.set()

    def resume(self) -> None:
        self._pause.clear()

    def stop_all(self) -> None:
        self._stop.set()
        self._pause.clear()

    def arm(self) -> None:
        self._stop.clear()

    def run(
        self, loop_id: str, tool: str, arguments: dict, risk: str, iterations: int = 1
    ) -> dict[str, object]:
        if risk != "SAFE":
            raise PermissionError("autonomous loops may execute SAFE tools only")
        count = max(1, min(int(iterations), self.max_iterations))
        started = time.monotonic()
        completed = 0
        for _ in range(count):
            if self._stop.is_set():
                break
            while self._pause.is_set() and not self._stop.is_set():
                time.sleep(0.05)
            if time.monotonic() - started >= self.max_seconds:
                break
            self.dispatcher.execute(tool, arguments)
            completed += 1
        return {
            "loop_id": loop_id,
            "completed": completed,
            "stopped": self._stop.is_set(),
            "budget_seconds": self.max_seconds,
        }


__all__ = ["AutonomousLoopController", "TaskLoopStore"]
