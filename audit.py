"""Local append-only audit logging with secret-safe structured records."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger(__name__)


class AuditLogger:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def record(self, event: str, **fields: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            **_sanitize(fields),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        lowered = value.lower()
        if any(secret in lowered for secret in ("api_key", "authorization", "bearer ")):
            return "[REDACTED]"
    return value


__all__ = ["AuditLogger"]
