from __future__ import annotations

import pytest

from skills.messaging_whatsapp import WhatsAppDesktopClient


def test_whatsapp_defaults_to_dry_run():
    client = WhatsAppDesktopClient()

    result = client.send_message("Atharva", "Hello")

    assert result == {"contact": "Atharva", "status": "dry_run_not_sent", "dry_run": True}


def test_whatsapp_validates_message_inputs():
    client = WhatsAppDesktopClient()
    with pytest.raises(ValueError, match="contact"):
        client.send_message("", "Hello")
    with pytest.raises(ValueError, match="empty"):
        client.send_message("Atharva", "")
    with pytest.raises(ValueError, match="4,096"):
        client.send_message("Atharva", "x" * 4097)


def test_whatsapp_diagnostics_fails_closed_on_non_windows():
    client = WhatsAppDesktopClient()
    result = client.diagnostics()
    assert result["available"] is False
    assert result["reason"] == "Windows host required"
