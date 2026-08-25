from __future__ import annotations

from pathlib import Path

import pytest

from desktop_control import DesktopController


class FakeBackend:
    def __init__(self):
        self.calls = []

    def click(self, *args, **kwargs):
        self.calls.append(("click", args, kwargs))

    def moveTo(self, *args, **kwargs):
        self.calls.append(("move", args, kwargs))

    def write(self, *args, **kwargs):
        self.calls.append(("write", args, kwargs))

    def press(self, *args, **kwargs):
        self.calls.append(("press", args, kwargs))


def test_desktop_control_requires_session_and_supports_bounded_actions(tmp_path: Path):
    backend = FakeBackend()
    controller = DesktopController(backend=backend, windows=True)
    with pytest.raises(PermissionError):
        controller.press("a")
    controller.start_session()
    controller.move(10, 20)
    controller.click(10, 20)
    controller.type_text("hello")
    controller.press("enter")
    assert len(backend.calls) == 4


def test_emergency_stop_cancels_and_rejects_unsafe_keys():
    controller = DesktopController(backend=FakeBackend(), windows=True)
    controller.start_session()
    controller.stop_all()
    with pytest.raises(PermissionError):
        controller.press("a")
    controller.start_session()
    with pytest.raises(ValueError):
        controller.press("f13")
    with pytest.raises(ValueError):
        controller.click(-1, 10)


def test_non_windows_fails_closed():
    controller = DesktopController(backend=None, windows=False)
    controller.start_session()
    with pytest.raises(RuntimeError, match="only on Windows"):
        controller.press("a")
