"""Opt-in screen capture with timeout and no default disk persistence."""

from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ScreenStatus:
    enabled: bool
    active: bool
    expires_at: float | None
    reason: str


class ScreenCapture:
    """Capture screenshots only during an explicit, time-limited session."""

    def __init__(
        self,
        timeout_seconds: float = 60.0,
        capture_factory: Callable[[], Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
        auto_expire: bool = False,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Screen timeout must be greater than zero")
        self.timeout_seconds = timeout_seconds
        self.capture_factory = capture_factory
        self.clock = clock
        self.auto_expire = bool(auto_expire)
        self._enabled = False
        self._expires_at: float | None = None
        self._reason = "disabled"

    def enable(self, reason: str = "user_request") -> ScreenStatus:
        self._enabled = True
        self._expires_at = self.clock() + self.timeout_seconds if self.auto_expire else None
        self._reason = reason[:200]
        return self.status()

    def disable(self, reason: str = "user_request") -> ScreenStatus:
        self._enabled = False
        self._expires_at = None
        self._reason = reason[:200]
        return self.status()

    def status(self) -> ScreenStatus:
        self._expire_if_needed()
        return ScreenStatus(self._enabled, self._enabled, self._expires_at, self._reason)

    def capture_png_base64(self) -> str:
        self._expire_if_needed()
        if not self._enabled:
            raise PermissionError("Screen awareness is disabled")
        if os.name != "nt" and self.capture_factory is None:
            raise RuntimeError("Screen capture requires a configured desktop capture backend")
        image_bytes = self._capture_png()
        if len(image_bytes) > 12_000_000:
            raise ValueError("Captured screenshot exceeds the safety size limit")
        return base64.b64encode(image_bytes).decode("ascii")

    def _capture_png(self) -> bytes:
        if self.capture_factory is not None:
            result = self.capture_factory()
            if not isinstance(result, bytes):
                raise TypeError("Capture backend must return PNG bytes")
            return result
        try:
            import mss
            import mss.tools
        except ImportError as exc:
            raise RuntimeError("mss is required for screen capture") from exc
        with mss.mss() as screen:
            monitor = screen.monitors[0]
            screenshot = screen.grab(monitor)
            return mss.tools.to_png(screenshot.rgb, screenshot.size)

    def _expire_if_needed(self) -> None:
        if (
            self.auto_expire
            and self._enabled
            and self._expires_at is not None
            and self.clock() >= self._expires_at
        ):
            self.disable("timeout")


__all__ = ["ScreenCapture", "ScreenStatus"]
