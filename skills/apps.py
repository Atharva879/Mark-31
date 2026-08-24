"""Allowlisted Windows application controls.

No model-provided executable path is accepted. Applications must be configured
by the user in the controller allowlist before they can be opened or closed.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    name: str
    executable: Path
    arguments: tuple[str, ...] = ()


class ApplicationController:
    def __init__(self, applications: dict[str, AppConfig] | None = None) -> None:
        self.applications = {key.lower(): value for key, value in (applications or {}).items()}

    def open(self, name: str) -> str:
        config = self._get(name)
        if os.name != "nt":
            raise RuntimeError("Application control is available only on Windows")
        if not config.executable.exists():
            raise FileNotFoundError(str(config.executable))
        subprocess.Popen([str(config.executable), *config.arguments], close_fds=True)
        return f"Opened {config.name}"

    def close(self, name: str) -> str:
        config = self._get(name)
        if os.name != "nt":
            raise RuntimeError("Application control is available only on Windows")
        # taskkill is invoked only with the configured executable name, never
        # with a model-generated command or freeform argument string.
        subprocess.run(
            ["taskkill", "/IM", config.executable.name, "/T"],
            check=False,
            capture_output=True,
            text=True,
        )
        return f"Close requested for {config.name}"

    def configured(self) -> list[str]:
        return sorted(config.name for config in self.applications.values())

    def _get(self, name: str) -> AppConfig:
        try:
            return self.applications[name.strip().lower()]
        except KeyError as exc:
            raise ValueError(f"Application is not allowlisted: {name}") from exc


__all__ = ["AppConfig", "ApplicationController"]
