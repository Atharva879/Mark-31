"""Read-only monitor callbacks for the local Jarvis scheduler."""

from __future__ import annotations

import hashlib
from typing import Any

from scheduler import Trigger
from skills.files import ScopedFileManager
from skills.web import WebClient


class MonitorRegistry:
    def __init__(self, web: WebClient, files: ScopedFileManager | None = None) -> None:
        self.web = web
        self.files = files

    def __call__(self, trigger: Trigger) -> tuple[str, bool, dict[str, Any]]:
        if trigger.kind == "web_url":
            return self._web(trigger)
        if trigger.kind == "file":
            return self._file(trigger)
        if trigger.kind == "reminder":
            return self._reminder(trigger)
        raise ValueError(f"Unsupported monitor kind: {trigger.kind}")

    def _web(self, trigger: Trigger) -> tuple[str, bool, dict[str, Any]]:
        url = str(trigger.payload["url"])
        max_chars = max(1, min(int(trigger.payload.get("max_chars", 12_000)), 100_000))
        payload = self.web.fetch_url(url, max_chars=max_chars)
        fingerprint = hashlib.sha256(payload["content"].encode("utf-8")).hexdigest()
        previous = trigger.payload.get("last_state", {})
        previous_fingerprint = previous.get("fingerprint") if isinstance(previous, dict) else None
        changed = bool(previous_fingerprint and previous_fingerprint != fingerprint)
        state = {
            "fingerprint": fingerprint,
            "content_type": payload["content_type"],
            "url": payload["url"],
        }
        summary = (
            f"{payload['url']} checked ({payload['content_type']}, {len(payload['content'])} chars)"
        )
        return summary, changed, state

    def _reminder(self, trigger: Trigger) -> tuple[str, bool, dict[str, Any]]:
        message = str(trigger.payload["message"]).strip()
        return f"Reminder: {message}", True, {"message": message}

    def _file(self, trigger: Trigger) -> tuple[str, bool, dict[str, Any]]:
        if self.files is None:
            raise PermissionError("File monitors require JARVIS_ALLOWED_ROOTS")
        path = str(trigger.payload["path"])
        metadata = self.files.metadata(path)
        if metadata["is_file"]:
            fingerprint = self.files.sha256(path)
        else:
            fingerprint = hashlib.sha256(str(metadata).encode("utf-8")).hexdigest()
        previous = trigger.payload.get("last_state", {})
        previous_fingerprint = previous.get("fingerprint") if isinstance(previous, dict) else None
        changed = bool(previous_fingerprint and previous_fingerprint != fingerprint)
        state = {
            "fingerprint": fingerprint,
            "path": metadata["path"],
            "size_bytes": metadata["size_bytes"],
        }
        summary = f"{metadata['path']} checked ({metadata['size_bytes']} bytes)"
        return summary, changed, state


__all__ = ["MonitorRegistry"]
