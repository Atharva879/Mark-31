from __future__ import annotations

from pathlib import Path

import pytest

from permissions import PermissionStore


class Clock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def test_permissions_are_disabled_by_default_and_revoke_independently(tmp_path: Path):
    clock = Clock()
    store = PermissionStore(tmp_path / "permissions.db", now=clock)
    assert store.check("camera") is False
    store.grant("camera", duration_seconds=60, reason="user_toggle")
    store.grant("screen", duration_seconds=60, reason="user_toggle")
    assert store.check("camera") is True
    store.revoke("camera")
    assert store.check("camera") is False
    assert store.check("screen") is True


def test_permissions_expire_and_persist(tmp_path: Path):
    clock = Clock()
    path = tmp_path / "permissions.db"
    store = PermissionStore(path, now=clock)
    store.grant("clipboard", duration_seconds=60)
    reopened = PermissionStore(path, now=clock)
    assert reopened.check("clipboard") is True
    clock.value += 60
    assert reopened.check("clipboard") is False
    assert reopened.get("clipboard").enabled is False


def test_permission_bounds_and_unknown_names_are_rejected(tmp_path: Path):
    store = PermissionStore(tmp_path / "permissions.db")
    with pytest.raises(ValueError, match="Unknown permission"):
        store.grant("unrestricted_shell")
    with pytest.raises(ValueError, match="duration"):
        store.grant("camera", duration_seconds=86_401)
    with pytest.raises(ValueError, match="Unknown permission"):
        store.check("unrestricted_shell")
