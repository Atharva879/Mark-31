"""Durable, bounded local conversation continuity for Jarvis."""

from __future__ import annotations

import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

_ALLOWED_ROLES = {"user", "assistant"}
_DEFAULT_PREFERENCES = {
    "display_name": "",
    "personality": "professional",
    "response_style": "concise",
}
_SECRET_PATTERN = re.compile(
    r"(?i)(api[_ -]?key|access[_ -]?token|secret|password|bearer)\s*[:=]\s*([^\s,;]+)"
)


@dataclass(frozen=True)
class ConversationTurn:
    role: str
    content: str
    created_at: float


@dataclass(frozen=True)
class ConversationSession:
    session_id: str
    title: str
    created_at: float
    updated_at: float
    archived: bool


class ConversationStore:
    """SQLite-backed sessions with bounded turn and preference storage."""

    def __init__(
        self,
        path: Path,
        now: Callable[[], float] | None = None,
        max_turn_chars: int = 12_000,
    ) -> None:
        if not 500 <= int(max_turn_chars) <= 50_000:
            raise ValueError("Conversation turn limit must be between 500 and 50,000 characters")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._now = now or time.time
        self.max_turn_chars = int(max_turn_chars)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS conversation_sessions ("
                "session_id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at REAL NOT NULL, "
                "updated_at REAL NOT NULL, archived INTEGER NOT NULL DEFAULT 0)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS conversation_turns ("
                "turn_id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, "
                "role TEXT NOT NULL, "
                "content TEXT NOT NULL, created_at REAL NOT NULL, "
                "FOREIGN KEY(session_id) REFERENCES conversation_sessions(session_id))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS conversation_preferences ("
                "key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS conversation_state ("
                "id INTEGER PRIMARY KEY CHECK(id=1), active_session_id TEXT NOT NULL)"
            )
            now = self._now()
            session_id = "session-main"
            connection.execute(
                "INSERT OR IGNORE INTO conversation_sessions("
                "session_id, title, created_at, updated_at, archived) "
                "VALUES (?, ?, ?, ?, 0)",
                (session_id, "Main conversation", now, now),
            )
            connection.execute(
                "INSERT OR IGNORE INTO conversation_state(id, active_session_id) VALUES (1, ?)",
                (session_id,),
            )
            for key, value in _DEFAULT_PREFERENCES.items():
                connection.execute(
                    "INSERT OR IGNORE INTO conversation_preferences("
                    "key, value, updated_at) VALUES (?, ?, ?)",
                    (key, value, now),
                )

    @staticmethod
    def _new_session_id() -> str:
        return f"session-{uuid.uuid4().hex[:16]}"

    @staticmethod
    def _redact(text: str) -> str:
        return _SECRET_PATTERN.sub(r"\1=[REDACTED]", text)

    def active_session_id(self) -> str:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT active_session_id FROM conversation_state WHERE id=1"
            ).fetchone()
        if row is None:
            raise RuntimeError("Active conversation session is unavailable")
        return str(row["active_session_id"])

    def create_session(
        self, title: str = "New conversation", activate: bool = True
    ) -> ConversationSession:
        title = self._redact(str(title).strip() or "New conversation")[:120]
        now = self._now()
        session_id = self._new_session_id()
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO conversation_sessions("
                "session_id, title, created_at, updated_at, archived) "
                "VALUES (?, ?, ?, ?, 0)",
                (session_id, title, now, now),
            )
            if activate:
                connection.execute(
                    "UPDATE conversation_state SET active_session_id=? WHERE id=1", (session_id,)
                )
        return ConversationSession(session_id, title, now, now, False)

    def set_active_session(self, session_id: str) -> ConversationSession:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM conversation_sessions WHERE session_id=? AND archived=0",
                (session_id,),
            ).fetchone()
            if row is None:
                raise ValueError("Conversation session does not exist or is archived")
            connection.execute(
                "UPDATE conversation_state SET active_session_id=? WHERE id=1", (session_id,)
            )
        return self._session_from_row(row)

    def archive_session(self, session_id: str) -> None:
        active = self.active_session_id()
        if session_id == active:
            raise ValueError("The active conversation cannot be archived")
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE conversation_sessions SET archived=1, updated_at=? WHERE session_id=?",
                (self._now(), session_id),
            )

    def list_sessions(
        self, include_archived: bool = False, limit: int = 50
    ) -> list[ConversationSession]:
        limit = max(1, min(int(limit), 100))
        query = "SELECT * FROM conversation_sessions "
        params: tuple[Any, ...]
        if not include_archived:
            query += "WHERE archived=0 "
            params = (limit,)
        else:
            params = (limit,)
        query += "ORDER BY updated_at DESC LIMIT ?"
        with self._lock, self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._session_from_row(row) for row in rows]

    def append(self, role: str, content: str, session_id: str | None = None) -> ConversationTurn:
        if role not in _ALLOWED_ROLES:
            raise ValueError("Conversation role must be user or assistant")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Conversation content cannot be empty")
        session_id = session_id or self.active_session_id()
        safe_content = self._redact(content.strip())[: self.max_turn_chars]
        now = self._now()
        with self._lock, self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM conversation_sessions WHERE session_id=? AND archived=0",
                (session_id,),
            ).fetchone()
            if exists is None:
                raise ValueError("Conversation session does not exist or is archived")
            connection.execute(
                "INSERT INTO conversation_turns(session_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?)",
                (session_id, role, safe_content, now),
            )
            connection.execute(
                "UPDATE conversation_sessions SET updated_at=? WHERE session_id=?",
                (now, session_id),
            )
        return ConversationTurn(role, safe_content, now)

    def recent_turns(
        self, session_id: str | None = None, limit: int = 12
    ) -> list[ConversationTurn]:
        session_id = session_id or self.active_session_id()
        limit = max(1, min(int(limit), 40))
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT role, content, created_at FROM conversation_turns "
                "WHERE session_id=? ORDER BY turn_id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [
            ConversationTurn(row["role"], row["content"], row["created_at"])
            for row in reversed(rows)
        ]

    def get_preferences(self) -> dict[str, str]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT key, value FROM conversation_preferences ORDER BY key"
            ).fetchall()
        preferences = _DEFAULT_PREFERENCES.copy()
        preferences.update({str(row["key"]): str(row["value"]) for row in rows})
        return preferences

    def set_preferences(self, values: dict[str, str]) -> dict[str, str]:
        allowed = set(_DEFAULT_PREFERENCES)
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"Unknown conversation preferences: {sorted(unknown)}")
        clean = {key: self._redact(str(value).strip())[:200] for key, value in values.items()}
        now = self._now()
        with self._lock, self._connect() as connection:
            for key, value in clean.items():
                connection.execute(
                    "INSERT INTO conversation_preferences(key, value, updated_at) VALUES (?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET "
                    "value=excluded.value, updated_at=excluded.updated_at",
                    (key, value, now),
                )
        return self.get_preferences()

    @staticmethod
    def _session_from_row(row: sqlite3.Row) -> ConversationSession:
        return ConversationSession(
            str(row["session_id"]),
            str(row["title"]),
            float(row["created_at"]),
            float(row["updated_at"]),
            bool(row["archived"]),
        )


__all__ = ["ConversationSession", "ConversationStore", "ConversationTurn"]
