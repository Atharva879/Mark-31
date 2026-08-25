"""Opt-in per-user Windows startup integration for Mark-31."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


class StartupManager:
    def __init__(
        self,
        entrypoint: Path,
        startup_dir: Path | None = None,
        windows: bool | None = None,
    ) -> None:
        self.entrypoint = Path(entrypoint).resolve()
        self.windows = os.name == "nt" if windows is None else bool(windows)
        self.startup_dir = Path(startup_dir) if startup_dir else self._default_startup_dir()
        self.launcher_path = self.startup_dir / "Mark31-Jarvis.cmd"

    @staticmethod
    def _default_startup_dir() -> Path:
        appdata = os.environ.get("APPDATA", "")
        if not appdata:
            return (
                Path.home()
                / "AppData"
                / "Roaming"
                / "Microsoft"
                / "Windows"
                / "Start Menu"
                / "Programs"
                / "Startup"
            )
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"

    def status(self) -> dict[str, object]:
        return {
            "supported": self.windows,
            "enabled": self.windows and self.launcher_path.is_file(),
            "path": str(self.launcher_path),
        }

    def enable(self) -> dict[str, object]:
        if not self.windows:
            raise RuntimeError("Windows startup is available only on Windows")
        if not self.entrypoint.is_file() or self.entrypoint.suffix.lower() != ".py":
            raise ValueError("Startup entrypoint must be an existing Python file")
        self.startup_dir.mkdir(parents=True, exist_ok=True)
        command = subprocess.list2cmdline([os.sys.executable, str(self.entrypoint)])
        content = f'@echo off\nstart "" {command}\n'
        self.launcher_path.write_text(content, encoding="utf-8", newline="\r\n")
        return self.status()

    def disable(self) -> dict[str, object]:
        if self.launcher_path.exists():
            self.launcher_path.unlink()
        return self.status()


__all__ = ["StartupManager"]
