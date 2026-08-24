"""WhatsApp Desktop adapter using Windows UI Automation.

The integration is intentionally isolated because desktop selectors can change
between WhatsApp releases. It defaults to dry-run and never accepts a freeform
executable or shell command.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class WhatsAppSendResult:
    contact: str
    status: str
    dry_run: bool


class WhatsAppDesktopClient:
    def __init__(
        self,
        dry_run: bool = True,
        window_title_re: str = r"WhatsApp.*",
        timeout_seconds: float = 10.0,
        desktop_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.dry_run = dry_run
        self.window_title_re = window_title_re
        self.timeout_seconds = timeout_seconds
        self.desktop_factory = desktop_factory

    def send_message(self, contact: str, content: str) -> dict[str, object]:
        contact = contact.strip() if isinstance(contact, str) else ""
        content = content.strip() if isinstance(content, str) else ""
        if not contact:
            raise ValueError("WhatsApp contact cannot be empty")
        if not content:
            raise ValueError("WhatsApp message cannot be empty")
        if len(content) > 4_096:
            raise ValueError("WhatsApp messages cannot exceed 4,096 characters")
        if self.dry_run:
            return WhatsAppSendResult(contact, "dry_run_not_sent", True).__dict__
        if os.name != "nt":
            raise RuntimeError("WhatsApp Desktop automation is available only on Windows")

        window = self._get_window()
        try:
            search = window.child_window(title_re=r"Search.*", control_type="Edit")
            search.wait("visible", timeout=self.timeout_seconds)
            search.set_focus()
            search.set_edit_text(contact)

            result = window.child_window(title=contact)
            result.wait("visible", timeout=self.timeout_seconds)
            result.click_input()

            message_box = _last_edit_control(window)
            message_box.wait("visible", timeout=self.timeout_seconds)
            message_box.set_focus()
            message_box.set_edit_text(content)
            message_box.type_keys("{ENTER}")
        except Exception as exc:
            raise RuntimeError(
                "WhatsApp UI selectors changed or the desktop app is not ready; "
                "run diagnostics and update the adapter selectors"
            ) from exc
        return WhatsAppSendResult(contact, "sent", False).__dict__

    def diagnostics(self) -> dict[str, object]:
        if os.name != "nt":
            return {"available": False, "reason": "Windows host required", "dry_run": self.dry_run}
        try:
            window = self._get_window()
            return {"available": True, "window_found": bool(window.exists()), "dry_run": self.dry_run}
        except Exception as exc:
            return {"available": False, "reason": str(exc)[:300], "dry_run": self.dry_run}

    def _get_window(self) -> Any:
        if self.desktop_factory is None:
            try:
                from pywinauto import Desktop
            except ImportError as exc:
                raise RuntimeError("pywinauto is required for WhatsApp Desktop automation") from exc
            factory = Desktop
        else:
            factory = self.desktop_factory
        window = factory(backend="uia").window(title_re=self.window_title_re)
        window.wait("exists", timeout=self.timeout_seconds)
        return window


def _last_edit_control(window: Any) -> Any:
    edits = window.descendants(control_type="Edit")
    if not edits:
        raise RuntimeError("WhatsApp message editor was not found")
    return edits[-1]


__all__ = ["WhatsAppDesktopClient", "WhatsAppSendResult"]
