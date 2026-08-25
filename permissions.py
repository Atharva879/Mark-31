"""Persistent, explicit capability permissions for the local Jarvis agent."""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

PERMISSION_LIMITS = {
    "screen": 24 * 60 * 60,
    "camera": 24 * 60 * 60,
    "active_window": 7 * 24 * 60 * 60,
    "clipboard": 60 * 60,
    "microphone": 60 * 60,
    "visual_thoughts": 24 * 60 * 60,
    "native_notifications": 30 * 24 * 60 * 60,
    "tray": 30 * 24 * 60 * 60,
    "calendar_read": 24 * 60 * 60,
    "task_write": 60 * 60,
    "email_draft": 60 * 60,
}


@dataclass(frozen=True)
class PermissionGrant:
    name: str
    enabled: bool
    expires_at: float | None
    reason: str
    updated_at: float


class PermissionStore:
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
                "CREATE TABLE IF NOT EXISTS permissions ("
                "name TEXT PRIMARY KEY, enabled INTEGER NOT NULL, expires_at REAL, "
                "reason TEXT NOT NULL, updated_at REAL NOT NULL)"
            )

    def grant(
        self, name: str, duration_seconds: int | None = None, reason: str = "user_request"
    ) -> PermissionGrant:
        if name not in PERMISSION_LIMITS:
            raise ValueError(f"Unknown permission: {name}")
        maximum = PERMISSION_LIMITS[name]
        duration = maximum if duration_seconds is None else int(duration_seconds)
        if not 1 <= duration <= maximum:
            raise ValueError(f"Permission {name} duration must be between 1 and {maximum} seconds")
        now = self._now()
        grant = PermissionGrant(name, True, now + duration, str(reason)[:200], now)
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO permissions(name, enabled, expires_at, reason, updated_at) "
                "VALUES (?, 1, ?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET enabled=1, "
                "expires_at=excluded.expires_at, reason=excluded.reason, "
                "updated_at=excluded.updated_at",
                (grant.name, grant.expires_at, grant.reason, grant.updated_at),
            )
        return grant

    def revoke(self, name: str, reason: str = "user_request") -> PermissionGrant:
        if name not in PERMISSION_LIMITS:
            raise ValueError(f"Unknown permission: {name}")
        now = self._now()
        grant = PermissionGrant(name, False, None, str(reason)[:200], now)
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO permissions(name, enabled, expires_at, reason, updated_at) "
                "VALUES (?, 0, NULL, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET enabled=0, expires_at=NULL, "
                "reason=excluded.reason, updated_at=excluded.updated_at",
                (name, grant.reason, now),
            )
        return grant

    def check(self, name: str) -> bool:
        if name not in PERMISSION_LIMITS:
            raise ValueError(f"Unknown permission: {name}")
        grant = self.get(name)
        if grant is None or not grant.enabled:
            return False
        if grant.expires_at is not None and self._now() >= grant.expires_at:
            self.revoke(name, "expired")
            return False
        return True

    def get(self, name: str) -> PermissionGrant | None:
        if name not in PERMISSION_LIMITS:
            raise ValueError(f"Unknown permission: {name}")
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT * FROM permissions WHERE name=?", (name,)).fetchone()
        if row is None:
            return None
        return PermissionGrant(
            str(row["name"]),
            bool(row["enabled"]),
            row["expires_at"],
            str(row["reason"]),
            float(row["updated_at"]),
        )

    def list(self) -> list[PermissionGrant]:
        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT * FROM permissions ORDER BY name").fetchall()
        result = []
        for row in rows:
            grant = PermissionGrant(
                str(row["name"]),
                bool(row["enabled"]),
                row["expires_at"],
                str(row["reason"]),
                float(row["updated_at"]),
            )
            if grant.enabled and grant.expires_at is not None and self._now() >= grant.expires_at:
                self.revoke(grant.name, "expired")
                grant = self.get(grant.name)
            if grant is not None:
                result.append(grant)
        return result


__all__ = ["PERMISSION_LIMITS", "PermissionGrant", "PermissionStore"]
