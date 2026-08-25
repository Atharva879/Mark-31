"""Bounded, interruptible desktop input control for explicit user-authorized sessions."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

_ALLOWED_KEYS = {
    "enter",
    "tab",
    "escape",
    "backspace",
    "delete",
    "space",
    "up",
    "down",
    "left",
    "right",
    "home",
    "end",
}


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def check(self) -> None:
        if self._event.is_set():
            raise RuntimeError("desktop action cancelled by emergency stop")


@dataclass
class DesktopSession:
    token: CancellationToken
    expires_at: float


class DesktopController:
    def __init__(self, backend=None, windows: bool | None = None, permission_check=None) -> None:
        self.windows = os.name == "nt" if windows is None else bool(windows)
        self.backend = backend
        self.permission_check = permission_check
        self.session: DesktopSession | None = None

    def _backend(self):
        if self.backend is not None:
            return self.backend
        if not self.windows:
            raise RuntimeError("desktop control is available only on Windows")
        try:
            import pyautogui  # type: ignore
        except ImportError as exc:
            raise RuntimeError("install the Windows desktop-control extras first") from exc
        self.backend = pyautogui
        return self.backend

    def start_session(self, duration_seconds: float = 60.0) -> dict[str, object]:
        if self.permission_check is not None and not self.permission_check():
            raise PermissionError("desktop Execute permission is not granted")
        duration = max(5.0, min(float(duration_seconds), 300.0))
        self.session = DesktopSession(CancellationToken(), time.monotonic() + duration)
        return self.status()

    def stop_all(self) -> dict[str, object]:
        if self.session:
            self.session.token.cancel()
        self.session = None
        return self.status()

    def status(self) -> dict[str, object]:
        active = self.session is not None and time.monotonic() < self.session.expires_at
        if self.session is not None and not active:
            self.session = None
        return {
            "supported": self.windows,
            "execute_enabled": active,
            "expires_at": self.session.expires_at if active and self.session else None,
        }

    def _ready(self) -> tuple[object, CancellationToken]:
        if not self.status()["execute_enabled"] or self.session is None:
            raise PermissionError("desktop Execute mode is disabled or expired")
        return self._backend(), self.session.token

    def click(self, x: int, y: int, button: str = "left") -> dict[str, object]:
        backend, token = self._ready()
        if button not in {"left", "right", "middle"} or not (
            0 <= int(x) <= 10000 and 0 <= int(y) <= 10000
        ):
            raise ValueError("invalid bounded click target")
        token.check()
        backend.click(int(x), int(y), button=button)
        return {"action": "click", "x": int(x), "y": int(y), "button": button}

    def move(self, x: int, y: int) -> dict[str, object]:
        backend, token = self._ready()
        if not (0 <= int(x) <= 10000 and 0 <= int(y) <= 10000):
            raise ValueError("invalid bounded pointer target")
        token.check()
        backend.moveTo(int(x), int(y), duration=0.1)
        return {"action": "move", "x": int(x), "y": int(y)}

    def type_text(self, text: str) -> dict[str, object]:
        backend, token = self._ready()
        if (
            not isinstance(text, str)
            or not text
            or len(text) > 2000
            or any(ord(char) < 32 and char not in "\n\t" for char in text)
        ):
            raise ValueError("text is empty, too long, or contains unsupported control characters")
        token.check()
        for index in range(0, len(text), 100):
            token.check()
            backend.write(text[index : index + 100], interval=0.01)
        return {"action": "type_text", "length": len(text)}

    def press(self, key: str) -> dict[str, object]:
        backend, token = self._ready()
        normalized = str(key).lower()
        if len(normalized) != 1 and normalized not in _ALLOWED_KEYS:
            raise ValueError("key is not in the safe key vocabulary")
        token.check()
        backend.press(normalized)
        return {"action": "press", "key": normalized}


__all__ = ["CancellationToken", "DesktopController"]
