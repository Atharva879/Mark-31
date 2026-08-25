from __future__ import annotations

from pathlib import Path

import pytest

from skills.window_manager import WindowManager


class FakeWindow:
    def __init__(self, handle, title):
        self.handle, self.title, self.calls = handle, title, []

    def window_text(self):
        return self.title

    def is_visible(self):
        return True

    def restore(self):
        self.calls.append("restore")

    def set_focus(self):
        self.calls.append("focus")

    def minimize(self):
        self.calls.append("minimize")

    def maximize(self):
        self.calls.append("maximize")

    def move_window(self, *args):
        self.calls.append(("move", args))

    def close(self):
        self.calls.append("close")


class FakeDesktop:
    def __init__(self):
        self.items = [FakeWindow(101, "Notepad"), FakeWindow(202, "Browser")]

    def windows(self):
        return self.items

    def window(self, handle):
        return next(item for item in self.items if item.handle == handle)


def test_window_manager_lists_and_controls_stable_handles(tmp_path: Path):
    del tmp_path
    backend = FakeDesktop()
    manager = WindowManager(backend=backend, windows=True)
    assert manager.list_windows()[0]["handle"] == 101
    manager.focus(101)
    manager.minimize(101)
    manager.maximize(101)
    manager.restore(101)
    manager.move_resize(101, 10, 20, 800, 600)
    manager.close(101)
    assert backend.items[0].calls[-1] == "close"


def test_window_manager_rejects_bad_handles_and_geometry():
    manager = WindowManager(backend=FakeDesktop(), windows=True)
    with pytest.raises(ValueError):
        manager.focus(0)
    with pytest.raises(ValueError):
        manager.move_resize(101, -1, 0, 800, 600)


def test_window_manager_fails_closed_off_windows():
    with pytest.raises(RuntimeError, match="only on Windows"):
        WindowManager(windows=False).list_windows()
