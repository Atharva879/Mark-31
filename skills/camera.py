"""Explicit, bounded camera capture for the local Jarvis desktop agent."""

from __future__ import annotations

import base64
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

MAX_CAPTURE_BYTES = 12_000_000


@dataclass(frozen=True)
class CameraStatus:
    enabled: bool
    active: bool
    expires_at: float | None
    reason: str
    device_index: int


class CameraCapture:
    """Capture one in-memory PNG only during an explicit bounded session."""

    def __init__(
        self,
        timeout_seconds: float = 60.0,
        device_index: int = 0,
        capture_factory: Callable[[], Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
        auto_expire: bool = False,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Camera timeout must be greater than zero")
        if not isinstance(device_index, int) or device_index < 0 or device_index > 16:
            raise ValueError("Camera device index must be between 0 and 16")
        self.timeout_seconds = float(timeout_seconds)
        self.device_index = device_index
        self.capture_factory = capture_factory
        self.clock = clock
        self.auto_expire = bool(auto_expire)
        self._enabled = False
        self._expires_at: float | None = None
        self._reason = "disabled"
        self._lock = threading.RLock()

    def enable(self, reason: str = "user_request") -> CameraStatus:
        with self._lock:
            self._enabled = True
            self._expires_at = self.clock() + self.timeout_seconds if self.auto_expire else None
            self._reason = str(reason)[:200]
            return self.status()

    def disable(self, reason: str = "user_request") -> CameraStatus:
        with self._lock:
            self._enabled = False
            self._expires_at = None
            self._reason = str(reason)[:200]
            return self.status()

    def status(self) -> CameraStatus:
        with self._lock:
            self._expire_if_needed()
            return CameraStatus(
                self._enabled,
                self._enabled,
                self._expires_at,
                self._reason,
                self.device_index,
            )

    def capture_png_base64(self) -> str:
        with self._lock:
            self._expire_if_needed()
            if not self._enabled:
                raise PermissionError("Camera awareness is disabled")
            if os.name != "nt" and self.capture_factory is None:
                raise RuntimeError("Camera capture requires a configured desktop camera backend")
            image_bytes = self._capture_png()
            if len(image_bytes) > MAX_CAPTURE_BYTES:
                raise ValueError("Captured camera frame exceeds the safety size limit")
            return base64.b64encode(image_bytes).decode("ascii")

    def _capture_png(self) -> bytes:
        if self.capture_factory is not None:
            result = self.capture_factory()
            if not isinstance(result, bytes):
                raise TypeError("Camera capture backend must return PNG bytes")
            return result
        capture = None
        try:
            import cv2

            capture = cv2.VideoCapture(self.device_index)
            if not capture.isOpened():
                raise RuntimeError(f"Camera device {self.device_index} could not be opened")
            success, frame = capture.read()
            if not success or frame is None:
                raise RuntimeError("Camera frame could not be read")
            success, encoded = cv2.imencode(".png", frame)
            if not success:
                raise RuntimeError("Camera frame could not be encoded as PNG")
            return encoded.tobytes()
        except ImportError as exc:
            raise RuntimeError("opencv-python is required for camera capture") from exc
        finally:
            if capture is not None:
                capture.release()

    def _expire_if_needed(self) -> None:
        if (
            self.auto_expire
            and self._enabled
            and self._expires_at is not None
            and self.clock() >= self._expires_at
        ):
            self._enabled = False
            self._expires_at = None
            self._reason = "timeout"


__all__ = ["CameraCapture", "CameraStatus", "MAX_CAPTURE_BYTES"]
