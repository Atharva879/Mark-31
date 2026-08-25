"""Read-only browser-like navigation built on the bounded web client."""

from __future__ import annotations

import re
from typing import Any

from skills.web import WebClient


class ReadOnlyBrowser:
    """Provide page navigation and search while refusing interactive browser actions."""

    def __init__(self, web_client: WebClient) -> None:
        self.web_client = web_client

    def search(self, query: str, max_results: int | None = None) -> list[dict[str, str]]:
        return self.web_client.search(query, max_results)

    def navigate(self, url: str, max_chars: int = 12_000) -> dict[str, Any]:
        payload = self.web_client.fetch_url(url, max_chars=max_chars)
        content = str(payload.get("content", ""))
        title = _extract_title(content)
        return {
            **payload,
            "title": title,
            "mode": "read_only",
            "scripts_executed": False,
            "forms_submitted": False,
            "downloads_started": False,
        }


def _extract_title(content: str) -> str:
    match = re.search(r"^\s*([^\n]{1,200})", content)
    return match.group(1).strip() if match else "Untitled page"


__all__ = ["ReadOnlyBrowser"]
