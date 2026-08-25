from __future__ import annotations

import base64

import pytest

from skills.camera import CameraCapture
from visual_presence import VisualObserver


class Clock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class FakeSource:
    def __init__(self, frame: bytes, active: bool = True) -> None:
        self.frame = frame
        self.active = active

    def status(self):
        return type("Status", (), {"active": self.active})()

    def capture_png_base64(self) -> str:
        return base64.b64encode(self.frame).decode("ascii")


def test_camera_requires_explicit_enablement_and_expires():
    clock = Clock()
    camera = CameraCapture(timeout_seconds=10, capture_factory=lambda: b"PNG", clock=clock)
    with pytest.raises(PermissionError, match="disabled"):
        camera.capture_png_base64()
    camera.enable("user_toggle")
    assert base64.b64decode(camera.capture_png_base64()) == b"PNG"
    clock.value = 111
    assert camera.status().active is False
    with pytest.raises(PermissionError, match="timed out"):
        camera.capture_png_base64()


def test_camera_rejects_bad_backend_and_oversized_frame():
    bad = CameraCapture(capture_factory=lambda: "not bytes")
    bad.enable()
    with pytest.raises(TypeError, match="PNG bytes"):
        bad.capture_png_base64()
    large = CameraCapture(capture_factory=lambda: b"x" * 12_000_001)
    large.enable()
    with pytest.raises(ValueError, match="size limit"):
        large.capture_png_base64()


def test_visual_observer_analyzes_only_new_frames_and_respects_cooldown():
    clock = Clock()
    source = FakeSource(b"frame-one")
    calls = []

    def analyzer(name: str, frame: bytes) -> str:
        calls.append((name, frame))
        return "bounded visual observation"

    observer = VisualObserver(
        {"camera": source}, analyzer, analysis_cooldown_seconds=60, clock=clock
    )
    first = observer.sample("camera")
    assert first is not None
    assert first.source == "camera"
    assert observer.sample("camera") is None
    source.frame = b"frame-two"
    assert observer.sample("camera") is None
    clock.value += 60
    second = observer.sample("camera")
    assert second is not None
    assert len(calls) == 2


def test_visual_observer_ignores_disabled_sources_and_rejects_unknown():
    source = FakeSource(b"frame", active=False)
    observer = VisualObserver({"screen": source}, lambda _name, _frame: "seen")
    assert observer.sample("screen") is None
    with pytest.raises(ValueError, match="Unknown visual source"):
        observer.sample("camera")
