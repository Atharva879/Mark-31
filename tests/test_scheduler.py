from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from scheduler import (
    MIN_INTERVAL_SECONDS,
    BackgroundScheduler,
    SchedulerStore,
    SchedulerValidationError,
    Trigger,
)
from skills.files import ScopedFileManager
from skills.monitoring import MonitorRegistry


class FakeWeb:
    def __init__(self, content: str) -> None:
        self.content = content

    def fetch_url(self, url: str, max_chars: int = 12_000) -> dict[str, object]:
        return {"url": url, "content_type": "text/plain", "content": self.content[:max_chars]}


def test_trigger_persists_and_reopens_with_bounds(tmp_path: Path):
    store = SchedulerStore(tmp_path / "scheduler.db")
    scheduler = BackgroundScheduler(store, lambda _trigger: ("ok", False, {}))
    with pytest.raises(SchedulerValidationError, match="between"):
        scheduler.create_trigger(
            "too fast", "file", MIN_INTERVAL_SECONDS - 1, {"path": str(tmp_path / "x")}
        )

    created = scheduler.create_trigger(
        "daily file", "file", MIN_INTERVAL_SECONDS, {"path": str(tmp_path)}
    )
    reopened = BackgroundScheduler(
        SchedulerStore(tmp_path / "scheduler.db"), lambda _trigger: ("ok", False, {})
    )
    records = reopened.list()
    assert len(records) == 1
    assert records[0]["trigger_id"] == created["trigger_id"]
    assert records[0]["enabled"] is True


def test_pause_resume_and_shutdown_lifecycle(tmp_path: Path):
    store = SchedulerStore(tmp_path / "scheduler.db")
    scheduler = BackgroundScheduler(store, lambda _trigger: ("ok", False, {}))
    trigger = scheduler.create_trigger(
        "pause me", "file", MIN_INTERVAL_SECONDS, {"path": str(tmp_path)}
    )
    scheduler.start()
    assert scheduler.status()["running"] is True
    scheduler.set_enabled(trigger["trigger_id"], False)
    assert scheduler.status()["enabled"] == 0
    scheduler.set_enabled(trigger["trigger_id"], True)
    assert scheduler.status()["enabled"] == 1
    scheduler.stop()
    assert scheduler.status()["running"] is False


def test_run_history_records_success_and_failure(tmp_path: Path):
    store = SchedulerStore(tmp_path / "scheduler.db")
    state = {"fail": False}

    def monitor(_trigger: Trigger):
        if state["fail"]:
            raise TimeoutError("bounded monitor timeout")
        return "checked", True, {"fingerprint": "abc"}

    scheduler = BackgroundScheduler(store, monitor)
    trigger = scheduler.create_trigger(
        "history", "file", MIN_INTERVAL_SECONDS, {"path": str(tmp_path)}
    )
    assert scheduler.run_once(trigger["trigger_id"])["status"] == "changed"
    state["fail"] = True
    assert scheduler.run_once(trigger["trigger_id"])["status"] == "failed"
    runs = store.recent_runs(10)
    assert [run["status"] for run in runs[:2]] == ["failed", "changed"]
    assert all(run["finished_at"] for run in runs[:2])


def test_same_trigger_cannot_run_concurrently(tmp_path: Path):
    store = SchedulerStore(tmp_path / "scheduler.db")
    entered = threading.Event()
    release = threading.Event()

    def monitor(_trigger: Trigger):
        entered.set()
        release.wait(2)
        return "done", False, {}

    scheduler = BackgroundScheduler(store, monitor)
    trigger = scheduler.create_trigger(
        "single flight", "file", MIN_INTERVAL_SECONDS, {"path": str(tmp_path)}
    )
    first = threading.Thread(target=scheduler.run_once, args=(trigger["trigger_id"],))
    first.start()
    assert entered.wait(1)
    second = scheduler.run_once(trigger["trigger_id"])
    assert second["status"] == "skipped"
    release.set()
    first.join(2)
    assert not first.is_alive()


def test_web_monitor_emits_only_real_changes():
    web = FakeWeb("version one")
    monitor = MonitorRegistry(web)
    trigger = Trigger(
        "abc",
        "site",
        "web_url",
        MIN_INTERVAL_SECONDS,
        True,
        {"url": "https://example.com"},
        time.time(),
    )
    summary, changed, state = monitor(trigger)
    assert "checked" in summary
    assert changed is False
    web.content = "version two"
    changed_trigger = Trigger(
        trigger.trigger_id,
        trigger.name,
        trigger.kind,
        trigger.interval_seconds,
        True,
        {"url": trigger.payload["url"], "last_state": state},
        time.time(),
    )
    _summary, changed, _state = monitor(changed_trigger)
    assert changed is True


def test_file_monitor_is_scoped_and_detects_hash_change(tmp_path: Path):
    target = tmp_path / "watched.txt"
    target.write_text("one", encoding="utf-8")
    monitor = MonitorRegistry(FakeWeb("unused"), ScopedFileManager([tmp_path]))
    trigger = Trigger(
        "file1", "file", "file", MIN_INTERVAL_SECONDS, True, {"path": str(target)}, time.time()
    )
    _summary, changed, state = monitor(trigger)
    assert changed is False
    target.write_text("two", encoding="utf-8")
    changed_trigger = Trigger(
        trigger.trigger_id,
        trigger.name,
        trigger.kind,
        trigger.interval_seconds,
        True,
        {"path": str(target), "last_state": state},
        time.time(),
    )
    _summary, changed, _state = monitor(changed_trigger)
    assert changed is True


def test_reminder_trigger_is_bounded_and_notifies(tmp_path: Path):
    notifications = []
    store = SchedulerStore(tmp_path / "scheduler.db")
    scheduler = BackgroundScheduler(
        store, MonitorRegistry(FakeWeb("unused")), notify=notifications.append
    )
    trigger = scheduler.create_trigger(
        "standup", "reminder", MIN_INTERVAL_SECONDS, {"message": "Review the activity feed"}
    )
    result = scheduler.run_once(trigger["trigger_id"])
    assert result["status"] == "changed"
    assert notifications == [
        "Scheduled reminder 'standup': scheduled. Reminder: Review the activity feed"
    ]


def test_web_monitor_rejects_non_http_url(tmp_path: Path):
    scheduler = BackgroundScheduler(
        SchedulerStore(tmp_path / "scheduler.db"), lambda _trigger: ("ok", False, {})
    )
    with pytest.raises(SchedulerValidationError, match="HTTP"):
        scheduler.create_trigger(
            "bad", "web_url", MIN_INTERVAL_SECONDS, {"url": "file:///etc/passwd"}
        )


def test_runtime_registers_scheduler_tools(tmp_path: Path, monkeypatch):
    from config import Settings
    from main import build_runtime

    monkeypatch.setenv("JARVIS_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("JARVIS_MEMORY_DB", str(tmp_path / "memory.db"))
    monkeypatch.setenv("JARVIS_VECTOR_DB", str(tmp_path / "vectors.db"))
    monkeypatch.setenv("JARVIS_SCHEDULER_DB", str(tmp_path / "scheduler.db"))
    _router, dispatcher, registry = build_runtime(Settings.from_env(), confirm=lambda _prompt: True)
    names = {tool.name for tool in registry.all()}
    assert {
        "create_monitor_trigger",
        "list_monitor_triggers",
        "monitor_status",
        "delete_monitor_trigger",
    }.issubset(names)
    result = dispatcher.dispatch(
        "create_monitor_trigger",
        {
            "name": "break",
            "kind": "reminder",
            "interval_seconds": MIN_INTERVAL_SECONDS,
            "payload": {"message": "Take a break"},
        },
    )
    assert result.executed is True
    assert registry.scheduler.list()[0]["kind"] == "reminder"
    deleted = dispatcher.dispatch(
        "delete_monitor_trigger", {"trigger_id": registry.scheduler.list()[0]["trigger_id"]}
    )
    assert deleted.executed is True
