"""Optional Windows system-tray presence for Jarvis."""

from __future__ import annotations

import os
import threading
from typing import Callable


class TrayController:
    """Start a tray icon only when explicitly enabled by configuration."""

    def __init__(self, on_show: Callable[[], None], on_quit: Callable[[], None]) -> None:
        self.on_show = on_show
        self.on_quit = on_quit
        self.icon = None
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        if os.name != "nt":
            return False
        try:
            import pystray
            from PIL import Image, ImageDraw
        except ImportError:
            return False
        image = Image.new("RGB", (64, 64), "#07111d")
        draw = ImageDraw.Draw(image)
        draw.ellipse((8, 8, 56, 56), outline="#22d3ee", width=4)
        menu = pystray.Menu(
            pystray.MenuItem("Show Jarvis", lambda _icon, _item: self.on_show()),
            pystray.MenuItem("Quit Jarvis", lambda _icon, _item: self.on_quit()),
        )
        self.icon = pystray.Icon("mark31-jarvis", image, "Mark-31 Jarvis", menu)
        self._thread = threading.Thread(target=self.icon.run, name="jarvis-tray", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        if self.icon is not None:
            self.icon.stop()
        self.icon = None
        self._thread = None


__all__ = ["TrayController"]
