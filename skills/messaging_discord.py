"""Official Discord bot API adapter for controlled message sends."""

from __future__ import annotations

from typing import Iterable

import requests


class DiscordClient:
    def __init__(
        self,
        bot_token: str,
        allowed_channel_ids: Iterable[str],
        timeout_seconds: float = 15.0,
        base_url: str = "https://discord.com/api/v10",
    ) -> None:
        if not bot_token.strip():
            raise ValueError("Discord bot token is required")
        channels = {str(channel_id).strip() for channel_id in allowed_channel_ids if str(channel_id).strip()}
        if not channels:
            raise ValueError("At least one allowed Discord channel ID is required")
        self._token = bot_token.strip()
        self.allowed_channel_ids = frozenset(channels)
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url.rstrip("/")

    def send_message(self, channel_id: str, content: str) -> dict:
        channel_id = str(channel_id).strip()
        if channel_id not in self.allowed_channel_ids:
            raise PermissionError("Discord channel is not allowlisted")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Discord message cannot be empty")
        if len(content) > 2_000:
            raise ValueError("Discord messages cannot exceed 2,000 characters")

        response = requests.post(
            f"{self.base_url}/channels/{channel_id}/messages",
            json={"content": content},
            headers={
                "Authorization": f"Bot {self._token}",
                "Content-Type": "application/json",
            },
            timeout=self.timeout_seconds,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Discord HTTP {response.status_code}: {response.text[:500]}")
        payload = response.json()
        return {"id": payload.get("id"), "channel_id": channel_id, "status": "sent"}


__all__ = ["DiscordClient"]
