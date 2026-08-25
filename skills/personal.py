"""Local-first personal-assistant tools with no external sends or account access."""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Task:
    task_id: int
    title: str
    notes: str
    due_at: str | None
    completed: bool
    created_at: float


@dataclass(frozen=True)
class CalendarEvent:
    summary: str
    start: str


@dataclass(frozen=True)
class EmailDraft:
    draft_id: int
    recipient: str
    subject: str
    body: str
    created_at: float


class PersonalStore:
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
                "CREATE TABLE IF NOT EXISTS tasks (task_id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "title TEXT NOT NULL, notes TEXT NOT NULL, due_at TEXT, "
                "completed INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS email_drafts ("
                "draft_id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "recipient TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL, "
                "created_at REAL NOT NULL)"
            )

    def create_task(self, title: str, notes: str = "", due_at: str | None = None) -> Task:
        title = str(title).strip()[:200]
        if not title:
            raise ValueError("Task title cannot be empty")
        now = self._now()
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO tasks(title, notes, due_at, completed, created_at) "
                "VALUES (?, ?, ?, 0, ?)",
                (
                    title,
                    str(notes).strip()[:2_000],
                    str(due_at).strip()[:80] if due_at else None,
                    now,
                ),
            )
            task_id = int(cursor.lastrowid)
        return Task(task_id, title, str(notes).strip()[:2_000], due_at, False, now)

    def list_tasks(self, include_completed: bool = False, limit: int = 100) -> list[Task]:
        limit = max(1, min(int(limit), 500))
        query = "SELECT * FROM tasks "
        params: tuple[object, ...] = (limit,)
        if not include_completed:
            query += "WHERE completed=0 "
        query += "ORDER BY completed ASC, COALESCE(due_at, '9999') ASC, task_id DESC LIMIT ?"
        with self._lock, self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [
            Task(
                int(row["task_id"]),
                str(row["title"]),
                str(row["notes"]),
                row["due_at"],
                bool(row["completed"]),
                float(row["created_at"]),
            )
            for row in rows
        ]

    def complete_task(self, task_id: int) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "UPDATE tasks SET completed=1 WHERE task_id=?", (int(task_id),)
            )
        return cursor.rowcount == 1

    def create_email_draft(self, recipient: str, subject: str, body: str) -> EmailDraft:
        recipient = str(recipient).strip()[:320]
        subject = str(subject).strip()[:200]
        body = str(body).strip()[:20_000]
        if not recipient or not subject or not body:
            raise ValueError("Recipient, subject, and body are required for a draft")
        now = self._now()
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO email_drafts(recipient, subject, body, created_at) "
                "VALUES (?, ?, ?, ?)",
                (recipient, subject, body, now),
            )
            draft_id = int(cursor.lastrowid)
        return EmailDraft(draft_id, recipient, subject, body, now)

    def list_email_drafts(self, limit: int = 50) -> list[EmailDraft]:
        limit = max(1, min(int(limit), 200))
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM email_drafts ORDER BY draft_id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            EmailDraft(
                int(row["draft_id"]),
                str(row["recipient"]),
                str(row["subject"]),
                str(row["body"]),
                float(row["created_at"]),
            )
            for row in rows
        ]


class ICalendarReader:
    def __init__(self, path: Path | None, max_events: int = 100) -> None:
        self.path = Path(path).expanduser() if path else None
        self.max_events = max(1, min(int(max_events), 500))

    def list_events(self) -> list[CalendarEvent]:
        if self.path is None:
            return []
        if not self.path.is_file():
            raise FileNotFoundError("Configured calendar file does not exist")
        if self.path.stat().st_size > 2_000_000:
            raise ValueError("Calendar file exceeds the configured size limit")
        return parse_icalendar(
            self.path.read_text(encoding="utf-8", errors="replace"), self.max_events
        )


def parse_icalendar(text: str, max_events: int = 100) -> list[CalendarEvent]:
    events: list[CalendarEvent] = []
    current_summary: str | None = None
    current_start: str | None = None
    in_event = False
    for raw_line in text.replace("\r\n", "\n").splitlines():
        line = raw_line.strip()
        if line == "BEGIN:VEVENT":
            in_event = True
            current_summary = None
            current_start = None
        elif line == "END:VEVENT" and in_event:
            if current_summary and current_start:
                events.append(CalendarEvent(current_summary[:200], current_start[:80]))
                if len(events) >= max_events:
                    break
            in_event = False
        elif in_event and line.startswith("SUMMARY"):
            current_summary = _ical_value(line)
        elif in_event and line.startswith("DTSTART"):
            current_start = _ical_value(line)
    return events


def _ical_value(line: str) -> str:
    value = line.split(":", 1)[1] if ":" in line else ""
    return value.replace("\\n", " ").replace("\\,", ",").replace("\\;", ";").strip()


__all__ = [
    "CalendarEvent",
    "EmailDraft",
    "ICalendarReader",
    "PersonalStore",
    "Task",
    "parse_icalendar",
]
