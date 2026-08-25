"""Explicit, bounded Windows system controls with injectable backends."""

from __future__ import annotations

import os
from pathlib import Path


class SystemController:
    def __init__(
        self, backend=None, windows: bool | None = None, allowed_roots: list[Path] | None = None
    ):
        self.backend = backend
        self.windows = os.name == "nt" if windows is None else bool(windows)
        self.allowed_roots = [Path(root).resolve() for root in (allowed_roots or [])]

    def _ready(self):
        if self.backend is not None:
            return self.backend
        if not self.windows:
            raise RuntimeError("system controls are available only on Windows")
        raise RuntimeError("Windows system-control backend is not installed")

    def _destination(self, raw: str) -> Path:
        path = Path(raw).expanduser().resolve()
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            raise ValueError("screenshot must use PNG or JPEG")
        if not any(path == root or root in path.parents for root in self.allowed_roots):
            raise PermissionError("screenshot destination is outside configured roots")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def screenshot(self, destination: str) -> dict[str, object]:
        path = self._destination(destination)
        backend = self._ready()
        backend.screenshot(str(path))
        return {"path": str(path), "saved": True}

    def set_wifi(self, enabled: bool) -> dict[str, object]:
        self._ready().set_wifi(bool(enabled))
        return {"control": "wifi", "enabled": bool(enabled)}

    def set_bluetooth(self, enabled: bool) -> dict[str, object]:
        self._ready().set_bluetooth(bool(enabled))
        return {"control": "bluetooth", "enabled": bool(enabled)}

    def set_volume(self, percent: int) -> dict[str, object]:
        value = max(0, min(int(percent), 100))
        self._ready().set_volume(value)
        return {"control": "volume", "percent": value}

    def set_brightness(self, percent: int) -> dict[str, object]:
        value = max(0, min(int(percent), 100))
        self._ready().set_brightness(value)
        return {"control": "brightness", "percent": value}


__all__ = ["SystemController"]
