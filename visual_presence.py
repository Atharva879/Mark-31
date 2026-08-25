"""Bounded visual sampling for explicit screen and camera sessions."""

from __future__ import annotations

import base64
import hashlib
import threading
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol


class CaptureSource(Protocol):
    def status(self): ...

    def capture_png_base64(self) -> str: ...


@dataclass(frozen=True)
class VisualThought:
    source: str
    text: str
    fingerprint: str
    created_at: float


@dataclass
class _SourceState:
    last_fingerprint: str | None = None
    last_analysis_at: float | None = None


class VisualObserver:
    """Sample active sources and analyze only meaningful visual changes."""

    def __init__(
        self,
        sources: Mapping[str, CaptureSource],
        analyzer: Callable[[str, bytes], str | None],
        analysis_cooldown_seconds: int = 600,
        max_thought_chars: int = 1_500,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 60 <= int(analysis_cooldown_seconds) <= 7 * 24 * 60 * 60:
            raise ValueError("Visual analysis cooldown must be between 60 and 604,800 seconds")
        if not 100 <= int(max_thought_chars) <= 8_000:
            raise ValueError("Visual thought limit must be between 100 and 8,000 characters")
        self.sources = dict(sources)
        self.analyzer = analyzer
        self.analysis_cooldown_seconds = int(analysis_cooldown_seconds)
        self.max_thought_chars = int(max_thought_chars)
        self.clock = clock
        self._state = {name: _SourceState() for name in self.sources}
        self._lock = threading.RLock()

    def reset(self, source: str | None = None) -> None:
        with self._lock:
            if source is None:
                for state in self._state.values():
                    state.last_fingerprint = None
                    state.last_analysis_at = None
                return
            if source not in self._state:
                raise ValueError(f"Unknown visual source: {source}")
            self._state[source] = _SourceState()

    def sample(self, source: str) -> VisualThought | None:
        with self._lock:
            if source not in self.sources:
                raise ValueError(f"Unknown visual source: {source}")
            controller = self.sources[source]
            if not controller.status().active:
                return None
            encoded = controller.capture_png_base64()
            frame = base64.b64decode(encoded, validate=True)
            fingerprint = hashlib.sha256(frame).hexdigest()
            state = self._state[source]
            now = self.clock()
            if state.last_fingerprint == fingerprint:
                return None
            if (
                state.last_analysis_at is not None
                and now - state.last_analysis_at < self.analysis_cooldown_seconds
            ):
                return None
            state.last_fingerprint = fingerprint
            state.last_analysis_at = now
            text = self.analyzer(source, frame)
            if not isinstance(text, str) or not text.strip():
                return None
            return VisualThought(source, text.strip()[: self.max_thought_chars], fingerprint, now)


__all__ = ["VisualObserver", "VisualThought"]
