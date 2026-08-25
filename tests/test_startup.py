from __future__ import annotations

from pathlib import Path

import pytest

from startup import StartupManager


def test_startup_manager_is_disabled_off_windows(tmp_path: Path):
    entrypoint = tmp_path / "main.py"
    entrypoint.write_text("print('ok')", encoding="utf-8")
    manager = StartupManager(entrypoint, tmp_path / "Startup", windows=False)
    assert manager.status()["supported"] is False
    with pytest.raises(RuntimeError, match="only on Windows"):
        manager.enable()


def test_startup_launcher_can_be_enabled_and_disabled(tmp_path: Path):
    entrypoint = tmp_path / "main.py"
    entrypoint.write_text("print('ok')", encoding="utf-8")
    startup_dir = tmp_path / "Startup"
    manager = StartupManager(entrypoint, startup_dir, windows=True)
    assert manager.status()["enabled"] is False
    assert manager.enable()["enabled"] is True
    assert "main.py" in manager.launcher_path.read_text(encoding="utf-8")
    assert manager.disable()["enabled"] is False
