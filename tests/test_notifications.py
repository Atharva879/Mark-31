from __future__ import annotations

from pathlib import Path

from notifications import NotificationCenter, NotificationStore


class Backend:
    def __init__(self):
        self.calls = []

    def show(self, title, body, level="info"):
        self.calls.append((title, body, level))


def test_notification_history_persists_and_redacts(tmp_path: Path):
    path = tmp_path / "notifications.db"
    backend = Backend()
    center = NotificationCenter(path, backend=backend, max_history=50, now=lambda: 100.0)
    record = center.notify("Jarvis", "api_key=secret-value", source="test")
    assert "secret-value" not in record.body
    assert backend.calls[0][1] == record.body
    reopened = NotificationStore(path)
    history = reopened.list()
    assert history[0].notification_id == record.notification_id
    assert history[0].read is False
    reopened.mark_all_read()
    assert reopened.list()[0].read is True


def test_notification_backend_failure_does_not_drop_local_history(tmp_path: Path):
    class BrokenBackend:
        def show(self, *_args, **_kwargs):
            raise RuntimeError("toast unavailable")

    center = NotificationCenter(tmp_path / "notifications.db", backend=BrokenBackend())
    center.notify("Jarvis", "Still available in history")
    assert center.history()[0].body == "Still available in history"
