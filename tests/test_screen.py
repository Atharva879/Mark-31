from __future__ import annotations

import base64

import pytest

from skills.screen import ScreenCapture


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value


def test_screen_capture_requires_explicit_enablement():
    screen = ScreenCapture(capture_factory=lambda: b"PNG")
    with pytest.raises(PermissionError, match="disabled"):
        screen.capture_png_base64()


def test_screen_capture_is_in_memory_and_expires():
    clock = FakeClock()
    screen = ScreenCapture(timeout_seconds=10, capture_factory=lambda: b"PNG", clock=clock)
    status = screen.enable("user_toggle")

    assert status.active is True
    assert base64.b64decode(screen.capture_png_base64()) == b"PNG"

    clock.value = 111.0
    assert screen.status().active is False
    with pytest.raises(PermissionError, match="timed out"):
        screen.capture_png_base64()


def test_screen_capture_rejects_oversized_payload():
    screen = ScreenCapture(capture_factory=lambda: b"x" * 12_000_001)
    screen.enable()
    with pytest.raises(ValueError, match="size limit"):
        screen.capture_png_base64()
