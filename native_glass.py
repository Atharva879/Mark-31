"""Optional Windows DWM composition for the Jarvis glass shell.

Tkinter remains the cross-platform UI layer. On Windows 11 this helper asks DWM
for a dark Mica backdrop; unsupported systems simply keep the layered Tk design.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Any


DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMSBT_MAINWINDOW = 3  # Mica on supported Windows 11 builds


def apply_native_glass(window: Any) -> bool:
    """Enable dark Mica composition for a Tk window when available."""
    if os.name != "nt":
        return False
    try:
        hwnd = wintypes.HWND(int(window.winfo_id()))
        dwmapi = ctypes.WinDLL("dwmapi")
        set_attribute = dwmapi.DwmSetWindowAttribute
        set_attribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        set_attribute.restype = wintypes.LONG
        dark = ctypes.c_int(1)
        backdrop = ctypes.c_int(DWMSBT_MAINWINDOW)
        dark_result = set_attribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(dark), ctypes.sizeof(dark)
        )
        backdrop_result = set_attribute(
            hwnd, DWMWA_SYSTEMBACKDROP_TYPE, ctypes.byref(backdrop), ctypes.sizeof(backdrop)
        )
        return dark_result == 0 and backdrop_result == 0
    except (AttributeError, OSError, TypeError, ValueError):
        return False


__all__ = ["apply_native_glass"]
