"""Bounded native Windows window management through pywinauto when available."""

from __future__ import annotations

import os


class WindowManager:
    def __init__(self, backend=None, windows: bool | None = None) -> None:
        self.backend = backend
        self.windows = os.name == "nt" if windows is None else bool(windows)

    def _backend(self):
        if self.backend is not None:
            return self.backend
        if not self.windows:
            raise RuntimeError("window management is available only on Windows")
        try:
            from pywinauto import Desktop
        except ImportError as exc:
            raise RuntimeError("install the Windows automation extras first") from exc
        self.backend = Desktop(backend="uia")
        return self.backend

    def list_windows(self) -> list[dict[str, object]]:
        windows = []
        for window in self._backend().windows():
            try:
                title = str(window.window_text())[:240]
                handle = int(window.handle)
                if title or handle:
                    windows.append(
                        {"handle": handle, "title": title, "visible": bool(window.is_visible())}
                    )
            except Exception:
                continue
        return windows[:200]

    def _window(self, handle: int):
        value = int(handle)
        if value <= 0:
            raise ValueError("window handle must be positive")
        try:
            return self._backend().window(handle=value)
        except Exception as exc:
            raise ValueError("window handle is not available") from exc

    def focus(self, handle: int) -> dict[str, object]:
        window = self._window(handle)
        window.restore()
        window.set_focus()
        return {"handle": int(handle), "action": "focus"}

    def minimize(self, handle: int) -> dict[str, object]:
        self._window(handle).minimize()
        return {"handle": int(handle), "action": "minimize"}

    def maximize(self, handle: int) -> dict[str, object]:
        self._window(handle).maximize()
        return {"handle": int(handle), "action": "maximize"}

    def restore(self, handle: int) -> dict[str, object]:
        self._window(handle).restore()
        return {"handle": int(handle), "action": "restore"}

    def move_resize(
        self, handle: int, x: int, y: int, width: int, height: int
    ) -> dict[str, object]:
        if not (
            0 <= int(x) <= 10000
            and 0 <= int(y) <= 10000
            and 200 <= int(width) <= 10000
            and 150 <= int(height) <= 10000
        ):
            raise ValueError("window geometry is outside safe bounds")
        self._window(handle).move_window(int(x), int(y), int(width), int(height))
        return {
            "handle": int(handle),
            "action": "move_resize",
            "x": int(x),
            "y": int(y),
            "width": int(width),
            "height": int(height),
        }

    def close(self, handle: int) -> dict[str, object]:
        self._window(handle).close()
        return {"handle": int(handle), "action": "close"}


__all__ = ["WindowManager"]
