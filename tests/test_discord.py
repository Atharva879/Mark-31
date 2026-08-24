from __future__ import annotations

import pytest

from skills.messaging_discord import DiscordClient


class FakeResponse:
    status_code = 200
    text = ""

    def json(self):
        return {"id": "message-123"}


def test_discord_send_uses_allowlisted_channel(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr("skills.messaging_discord.requests.post", fake_post)
    client = DiscordClient("bot-secret", ["123"])

    result = client.send_message("123", "Hello from Jarvis")

    assert result == {"id": "message-123", "channel_id": "123", "status": "sent"}
    assert calls[0][0].endswith("/channels/123/messages")
    assert calls[0][1]["json"] == {"content": "Hello from Jarvis"}
    assert calls[0][1]["headers"]["Authorization"] == "Bot bot-secret"


def test_discord_rejects_unallowlisted_channel():
    client = DiscordClient("bot-secret", ["123"])
    with pytest.raises(PermissionError, match="not allowlisted"):
        client.send_message("999", "Do not send")


def test_discord_rejects_oversized_message():
    client = DiscordClient("bot-secret", ["123"])
    with pytest.raises(ValueError, match="2,000"):
        client.send_message("123", "x" * 2001)
