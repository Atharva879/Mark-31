from __future__ import annotations

from pathlib import Path

import pytest

from conversation import ConversationStore


def test_conversation_persists_active_session_and_recent_turns(tmp_path: Path):
    path = tmp_path / "conversation.db"
    store = ConversationStore(path)
    store.append("user", "Remember this context")
    store.append("assistant", "I will keep it in this session.")

    reopened = ConversationStore(path)
    turns = reopened.recent_turns()
    assert [turn.role for turn in turns] == ["user", "assistant"]
    assert turns[0].content == "Remember this context"
    assert reopened.active_session_id() == store.active_session_id()
    assert len(reopened.list_sessions()) == 1


def test_conversation_redacts_secret_like_values_and_bounds_content(tmp_path: Path):
    store = ConversationStore(tmp_path / "conversation.db", max_turn_chars=500)
    turn = store.append("user", "api_key=super-secret-value " + "x" * 900)
    assert "super-secret-value" not in turn.content
    assert "[REDACTED]" in turn.content
    assert len(turn.content) <= 500


def test_sessions_can_be_created_switched_and_archived_safely(tmp_path: Path):
    store = ConversationStore(tmp_path / "conversation.db")
    first = store.active_session_id()
    second = store.create_session("Project planning")
    assert store.active_session_id() == second.session_id
    store.set_active_session(first)
    store.archive_session(second.session_id)
    assert second.session_id not in {item.session_id for item in store.list_sessions()}
    with pytest.raises(ValueError, match="active conversation"):
        store.archive_session(first)
    with pytest.raises(ValueError, match="archived"):
        store.set_active_session(second.session_id)


def test_preferences_are_persistent_and_reject_unknown_keys(tmp_path: Path):
    path = tmp_path / "conversation.db"
    store = ConversationStore(path)
    updated = store.set_preferences(
        {"display_name": "Atharva", "personality": "warm", "response_style": "balanced"}
    )
    assert updated["display_name"] == "Atharva"
    reopened = ConversationStore(path)
    assert reopened.get_preferences()["personality"] == "warm"
    with pytest.raises(ValueError, match="Unknown"):
        store.set_preferences({"unsafe_mode": "true"})
