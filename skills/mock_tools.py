"""Side-effect-free tools used by the first vertical slice and its tests."""

from __future__ import annotations

from datetime import UTC, datetime


def get_current_time() -> str:
    return datetime.now(UTC).isoformat()


def echo_status(message: str) -> str:
    return f"Status: {message}"


def remember_note(note: str) -> str:
    """Milestone 1 placeholder; durable memory is introduced in Milestone 4."""
    return f"Note accepted for this session: {note}"


def clear_sensitive_action(target: str) -> str:
    """Test-only sensitive tool; it performs no real action."""
    return f"Would clear: {target}"


__all__ = ["clear_sensitive_action", "echo_status", "get_current_time", "remember_note"]
