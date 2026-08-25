from pathlib import Path

import pytest

from system_controls import SystemController


class FakeSystem:
    def __init__(self):
        self.calls = []

    def screenshot(self, path):
        self.calls.append(("screenshot", path))

    def set_wifi(self, value):
        self.calls.append(("wifi", value))

    def set_bluetooth(self, value):
        self.calls.append(("bluetooth", value))

    def set_volume(self, value):
        self.calls.append(("volume", value))

    def set_brightness(self, value):
        self.calls.append(("brightness", value))


def test_system_controls_are_bounded_and_scoped(tmp_path: Path):
    backend = FakeSystem()
    controller = SystemController(backend, windows=True, allowed_roots=[tmp_path])
    result = controller.screenshot(str(tmp_path / "screen.png"))
    controller.set_wifi(True)
    controller.set_bluetooth(False)
    controller.set_volume(150)
    controller.set_brightness(-2)
    assert result["saved"] is True
    assert ("volume", 100) in backend.calls and ("brightness", 0) in backend.calls
    with pytest.raises(PermissionError):
        controller.screenshot(str(tmp_path.parent / "bad.png"))


def test_system_controls_fail_closed_without_backend():
    controller = SystemController(None, windows=False)
    with pytest.raises(RuntimeError, match="only on Windows"):
        controller.set_wifi(True)
