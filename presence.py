"""Bounded proactive presence for the local Jarvis desktop agent.

Presence is an output-only subsystem. It can select a short notification from
approved local context, but it cannot invoke tools, inspect arbitrary data, or
change system state.
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class PresenceLimits:
    idle_seconds: int = 60
    cooldown_seconds: int = 10 * 60
    hourly_limit: int = 2
    daily_limit: int = 20
    recent_message_window: int = 24

    def __post_init__(self) -> None:
        if not 60 <= int(self.idle_seconds) <= 24 * 60 * 60:
            raise ValueError("Presence idle_seconds must be between 60 and 86,400")
        if not 10 * 60 <= int(self.cooldown_seconds) <= 7 * 24 * 60 * 60:
            raise ValueError("Presence cooldown_seconds must be between 600 and 604,800")
        if not 1 <= int(self.hourly_limit) <= 24:
            raise ValueError("Presence hourly_limit must be between 1 and 24")
        if not 1 <= int(self.daily_limit) <= 100:
            raise ValueError("Presence daily_limit must be between 1 and 100")
        if not 1 <= int(self.recent_message_window) <= 100:
            raise ValueError("Presence recent_message_window must be between 1 and 100")


@dataclass(frozen=True)
class PresenceMessage:
    text: str
    category: str
    reason: str
    fingerprint: str
    created_at: float


class PresenceStore:
    """SQLite state and bounded history for proactive output."""

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
                "CREATE TABLE IF NOT EXISTS presence_state ("
                "id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL, "
                "silent INTEGER NOT NULL, "
                "last_activity_at REAL NOT NULL, last_emission_at REAL, updated_at REAL NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS presence_messages ("
                "message_id INTEGER PRIMARY KEY AUTOINCREMENT, fingerprint TEXT NOT NULL, "
                "category TEXT NOT NULL, "
                "text TEXT NOT NULL, created_at REAL NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS presence_events ("
                "event_id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, "
                "summary TEXT NOT NULL, "
                "priority INTEGER NOT NULL, created_at REAL NOT NULL)"
            )
            now = self._now()
            connection.execute(
                "INSERT OR IGNORE INTO presence_state("
                "id, enabled, silent, last_activity_at, last_emission_at, updated_at) "
                "VALUES (1, 1, 0, ?, NULL, ?)",
                (now, now),
            )

    def state(self) -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT * FROM presence_state WHERE id=1").fetchone()
        if row is None:
            raise RuntimeError("Presence state is unavailable")
        return dict(row)

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE presence_state SET enabled=?, updated_at=? WHERE id=1",
                (int(bool(enabled)), self._now()),
            )
        return self.state()

    def set_silent(self, silent: bool) -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE presence_state SET silent=?, updated_at=? WHERE id=1",
                (int(bool(silent)), self._now()),
            )
        return self.state()

    def mark_activity(self, at: float | None = None) -> None:
        timestamp = self._now() if at is None else float(at)
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE presence_state SET last_activity_at=?, updated_at=? WHERE id=1",
                (timestamp, timestamp),
            )

    def record_event(
        self, category: str, summary: str, priority: int = 50, at: float | None = None
    ) -> None:
        if not isinstance(category, str) or not category.strip():
            raise ValueError("Presence event category cannot be empty")
        if not isinstance(summary, str) or not summary.strip():
            return
        timestamp = self._now() if at is None else float(at)
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO presence_events(category, summary, priority, created_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    category.strip()[:60],
                    summary.strip()[:500],
                    max(0, min(int(priority), 100)),
                    timestamp,
                ),
            )
            connection.execute(
                "DELETE FROM presence_events WHERE event_id NOT IN "
                "(SELECT event_id FROM presence_events ORDER BY created_at DESC LIMIT 100)",
            )

    def latest_event(self, since: float | None = None) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            if since is None:
                row = connection.execute(
                    "SELECT * FROM presence_events ORDER BY priority DESC, created_at DESC LIMIT 1"
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM presence_events WHERE created_at>=? "
                    "ORDER BY priority DESC, created_at DESC LIMIT 1",
                    (float(since),),
                ).fetchone()
        return dict(row) if row else None

    def recent_messages(self, limit: int) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT fingerprint, category, text, created_at "
                "FROM presence_messages ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def emission_counts(self, now: float | None = None) -> dict[str, int | float | None]:
        timestamp = self._now() if now is None else float(now)
        local_day = datetime.fromtimestamp(timestamp).date().isoformat()
        hour_start = timestamp - 60 * 60
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT last_emission_at FROM presence_state WHERE id=1"
            ).fetchone()
            hourly = connection.execute(
                "SELECT COUNT(*) AS count FROM presence_messages WHERE created_at>=?", (hour_start,)
            ).fetchone()["count"]
            daily = connection.execute(
                "SELECT COUNT(*) AS count FROM presence_messages "
                "WHERE date(created_at, 'unixepoch', 'localtime')=?",
                (local_day,),
            ).fetchone()["count"]
        return {
            "last_emission_at": row["last_emission_at"] if row else None,
            "hourly": int(hourly),
            "daily": int(daily),
        }

    def record_emission(self, message: PresenceMessage) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO presence_messages(fingerprint, category, text, created_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    message.fingerprint,
                    message.category[:60],
                    message.text[:1_000],
                    message.created_at,
                ),
            )
            connection.execute(
                "UPDATE presence_state SET last_emission_at=?, updated_at=? WHERE id=1",
                (message.created_at, message.created_at),
            )
            connection.execute(
                "DELETE FROM presence_messages WHERE message_id NOT IN "
                "(SELECT message_id FROM presence_messages ORDER BY created_at DESC LIMIT 500)",
            )


class PresenceEngine:
    """Select at most one useful proactive message per evaluation."""

    def __init__(
        self,
        store: PresenceStore,
        limits: PresenceLimits | None = None,
        now: Callable[[], float] | None = None,
        audit: Callable[..., None] | None = None,
    ) -> None:
        self.store = store
        self.limits = limits or PresenceLimits()
        self._now = now or time.time
        self.audit = audit or (lambda _event, **_fields: None)
        self._lock = threading.Lock()

    def mark_activity(self, at: float | None = None) -> None:
        self.store.mark_activity(at)

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        return self.store.set_enabled(enabled)

    def set_silent(self, silent: bool) -> dict[str, Any]:
        return self.store.set_silent(silent)

    def observe_event(self, category: str, summary: str, priority: int = 50) -> None:
        self.store.record_event(category, summary, priority, self._now())

    def status(self) -> dict[str, Any]:
        state = self.store.state()
        counts = self.store.emission_counts(self._now())
        return {**state, **counts, "limits": self.limits.__dict__.copy()}

    def consider(self, context: Mapping[str, Any] | None = None) -> PresenceMessage | None:
        timestamp = self._now()
        with self._lock:
            state = self.store.state()
            if not state["enabled"] or state["silent"]:
                return None
            if timestamp - float(state["last_activity_at"]) < self.limits.idle_seconds:
                return None
            counts = self.store.emission_counts(timestamp)
            last_emission = counts["last_emission_at"]
            if (
                last_emission is not None
                and timestamp - float(last_emission) < self.limits.cooldown_seconds
            ):
                return None
            if (
                int(counts["hourly"]) >= self.limits.hourly_limit
                or int(counts["daily"]) >= self.limits.daily_limit
            ):
                return None
            recent = self.store.recent_messages(self.limits.recent_message_window)
            used_fingerprints = {str(item["fingerprint"]) for item in recent}
            candidates = self._candidates(context or {})
            for category, reason, text in candidates:
                fingerprint = hashlib.sha256(f"{category}:{text}".encode("utf-8")).hexdigest()
                if fingerprint in used_fingerprints:
                    continue
                message = PresenceMessage(text, category, reason, fingerprint, timestamp)
                self.store.record_emission(message)
                self.audit(
                    "presence_emitted",
                    category=message.category,
                    reason=message.reason,
                    fingerprint=message.fingerprint,
                )
                return message
        return None

    def _candidates(self, context: Mapping[str, Any]) -> list[tuple[str, str, str]]:
        candidates: list[tuple[str, str, str]] = []
        event = self.store.latest_event(since=self._now() - 30 * 60)
        if event:
            candidates.append(
                (
                    "event",
                    f"recent_{event['category']}",
                    f"I noticed something worth mentioning: {str(event['summary'])[:420]}",
                )
            )
        if context.get("scheduler_enabled"):
            candidates.append(
                (
                    "awareness",
                    "scheduler_active",
                    "I’m keeping watch over the monitors you enabled. "
                    "I’ll let you know if something meaningful changes.",
                )
            )
        candidates.extend(
            [
                (
                    "presence",
                    "quiet_ready",
                    "Everything is quiet right now. I’m here and ready whenever you need me.",
                ),
                (
                    "presence",
                    "quiet_observing",
                    "No new activity to report. I’m keeping the channel clear and staying ready.",
                ),
                (
                    "presence",
                    "quiet_offer",
                    "It’s been calm for a little while. "
                    "If you want, you can give me a task or open Chat Mode.",
                ),
                (
                    "presence",
                    "quiet_checkin",
                    "Still here. Nothing needs your attention from my side at the moment.",
                ),
            ]
        )
        return candidates


__all__ = ["PresenceEngine", "PresenceLimits", "PresenceMessage", "PresenceStore"]
