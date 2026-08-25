"""Bounded local notification history and optional native Windows toasts."""

from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

_SECRET_PATTERN = re.compile(
    r"(?i)(api[_ -]?key|access[_ -]?token|secret|password|bearer)\s*[:=]\s*([^\s,;]+)"
)


@dataclass(frozen=True)
class NotificationRecord:
    notification_id: int
    title: str
    body: str
    level: str
    source: str
    created_at: float
    read: bool


class NotificationBackend(Protocol):
    def show(self, title: str, body: str, level: str = "info") -> None: ...


class NativeToastBackend:
    """Use the optional winotify package for Windows toast notifications."""

    def __init__(self, app_id: str = "Mark-31 Jarvis") -> None:
        self.app_id = app_id[:64]

    def show(self, title: str, body: str, level: str = "info") -> None:
        if os.name != "nt":
            raise RuntimeError("Native Windows notifications are available only on Windows")
        try:
            from winotify import Notification
        except ImportError as exc:
            raise RuntimeError("winotify is required for native Windows notifications") from exc
        Notification(app_id=self.app_id, title=title[:80], msg=body[:1_000]).show()


class NotificationStore:
    def __init__(self, path: Path, max_history: int = 500) -> None:
        if not 50 <= int(max_history) <= 10_000:
            raise ValueError("Notification history must be between 50 and 10,000 records")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_history = int(max_history)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS notifications ("
                "notification_id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, "
                "body TEXT NOT NULL, level TEXT NOT NULL, source TEXT NOT NULL, "
                "created_at REAL NOT NULL, read INTEGER NOT NULL DEFAULT 0)"
            )

    def add(
        self, title: str, body: str, level: str, source: str, created_at: float
    ) -> NotificationRecord:
        safe_title = _SECRET_PATTERN.sub(r"\1=[REDACTED]", str(title).strip())[:80] or "Jarvis"
        safe_body = _SECRET_PATTERN.sub(r"\1=[REDACTED]", str(body).strip())[:2_000]
        safe_level = level if level in {"info", "warning", "error"} else "info"
        safe_source = str(source).strip()[:80]
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO notifications(title, body, level, source, created_at, read) "
                "VALUES (?, ?, ?, ?, ?, 0)",
                (safe_title, safe_body, safe_level, safe_source, created_at),
            )
            connection.execute(
                "DELETE FROM notifications WHERE notification_id NOT IN "
                "(SELECT notification_id FROM notifications ORDER BY notification_id DESC LIMIT ?)",
                (self.max_history,),
            )
            notification_id = int(cursor.lastrowid)
        return NotificationRecord(
            notification_id, safe_title, safe_body, safe_level, safe_source, created_at, False
        )

    def list(self, limit: int = 100, unread_only: bool = False) -> list[NotificationRecord]:
        limit = max(1, min(int(limit), self.max_history))
        query = "SELECT * FROM notifications "
        params: tuple[object, ...]
        if unread_only:
            query += "WHERE read=0 "
        params = (limit,)
        query += "ORDER BY notification_id DESC LIMIT ?"
        with self._lock, self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [
            NotificationRecord(
                int(row["notification_id"]),
                str(row["title"]),
                str(row["body"]),
                str(row["level"]),
                str(row["source"]),
                float(row["created_at"]),
                bool(row["read"]),
            )
            for row in rows
        ]

    def mark_all_read(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("UPDATE notifications SET read=1 WHERE read=0")


class NotificationCenter:
    def __init__(
        self,
        path: Path,
        backend: NotificationBackend | None = None,
        max_history: int = 500,
        now: Callable[[], float] | None = None,
    ) -> None:
        self.store = NotificationStore(path, max_history)
        self.backend = backend
        self._now = now or time.time

    def notify(
        self, title: str, body: str, level: str = "info", source: str = "system"
    ) -> NotificationRecord:
        record = self.store.add(title, body, level, source, self._now())
        if self.backend is not None:
            try:
                self.backend.show(record.title, record.body, record.level)
            except Exception:
                # History remains available when toast registration is unavailable.
                pass
        return record

    def history(self, limit: int = 100, unread_only: bool = False) -> list[NotificationRecord]:
        return self.store.list(limit, unread_only)

    def mark_all_read(self) -> None:
        self.store.mark_all_read()


__all__ = ["NativeToastBackend", "NotificationCenter", "NotificationRecord", "NotificationStore"]
