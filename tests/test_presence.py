from __future__ import annotations

import threading
from pathlib import Path

from presence import PresenceEngine, PresenceLimits, PresenceStore


class Clock:
    def __init__(self, value: float = 1_700_000_000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def test_presence_waits_for_idle_threshold_and_emits_once(tmp_path: Path):
    clock = Clock()
    store = PresenceStore(tmp_path / "presence.db", now=clock)
    audit_events = []
    engine = PresenceEngine(
        store,
        now=clock,
        audit=lambda event, **fields: audit_events.append((event, fields)),
    )
    engine.mark_activity()
    clock.value += 59
    assert engine.consider() is None
    clock.value += 1
    message = engine.consider()
    assert message is not None
    assert message.category == "presence"
    assert audit_events[0][0] == "presence_emitted"
    assert "fingerprint" in audit_events[0][1]
    assert "text" not in audit_events[0][1]
    assert engine.consider() is None


def test_silence_override_wins_and_persists(tmp_path: Path):
    clock = Clock()
    path = tmp_path / "presence.db"
    store = PresenceStore(path, now=clock)
    engine = PresenceEngine(store, now=clock)
    engine.set_silent(True)
    clock.value += 120
    assert engine.consider() is None
    reopened = PresenceEngine(PresenceStore(path, now=clock), now=clock)
    assert reopened.status()["silent"] == 1
    reopened.set_silent(False)
    assert reopened.consider() is not None


def test_cooldown_hourly_and_daily_limits_are_enforced(tmp_path: Path):
    clock = Clock()
    store = PresenceStore(tmp_path / "presence.db", now=clock)
    limits = PresenceLimits(idle_seconds=60, cooldown_seconds=600, hourly_limit=2, daily_limit=2)
    engine = PresenceEngine(store, limits, now=clock)
    engine.mark_activity()
    clock.value += 60
    assert engine.consider() is not None
    clock.value += 601
    engine.mark_activity(clock.value - 601)
    assert engine.consider() is not None
    clock.value += 601
    engine.mark_activity(clock.value - 601)
    assert engine.consider() is None


def test_repetition_protection_rotates_candidates(tmp_path: Path):
    clock = Clock()
    store = PresenceStore(tmp_path / "presence.db", now=clock)
    limits = PresenceLimits(
        idle_seconds=60,
        cooldown_seconds=600,
        hourly_limit=10,
        daily_limit=10,
        recent_message_window=24,
    )
    engine = PresenceEngine(store, limits, now=clock)
    messages = []
    for _ in range(4):
        engine.mark_activity(clock.value - 100)
        message = engine.consider({"scheduler_enabled": True})
        assert message is not None
        messages.append(message.text)
        clock.value += 601
    assert len(set(messages)) == 4


def test_event_context_is_prioritized_over_ambient_presence(tmp_path: Path):
    clock = Clock()
    store = PresenceStore(tmp_path / "presence.db", now=clock)
    engine = PresenceEngine(store, PresenceLimits(idle_seconds=60), now=clock)
    engine.observe_event("scheduler", "A watched file changed", priority=90)
    engine.mark_activity(clock.value - 120)
    message = engine.consider()
    assert message is not None
    assert message.category == "event"
    assert "watched file changed" in message.text


def test_concurrent_consider_emits_only_one_message(tmp_path: Path):
    clock = Clock()
    store = PresenceStore(tmp_path / "presence.db", now=clock)
    engine = PresenceEngine(
        store,
        PresenceLimits(idle_seconds=60, cooldown_seconds=600, hourly_limit=1),
        now=clock,
    )
    engine.mark_activity(clock.value - 70)
    results = []

    def worker():
        results.append(engine.consider())

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(item is not None for item in results) == 1
