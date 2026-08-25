from __future__ import annotations

from pathlib import Path
from jarvis_secrets import SecretStore

import pytest

from backup import BackupManager


class FakeDPAPI:
    @staticmethod
    def CryptProtectData(data, *_args):
        return (b"description", b"enc:" + data)

    @staticmethod
    def CryptUnprotectData(data, *_args):
        return (b"description", data.removeprefix(b"enc:"))


def test_secret_store_uses_backend_and_never_plaintext(tmp_path: Path):
    store = SecretStore(tmp_path / "secrets.json", backend=FakeDPAPI)
    store.set("provider_key", "top-secret")
    assert store.get("provider_key") == "top-secret"
    assert "top-secret" not in (tmp_path / "secrets.json").read_text(encoding="utf-8")
    assert store.delete("provider_key") is True
    assert store.get("provider_key") is None


def test_secret_store_fails_closed_without_backend(tmp_path: Path):
    with pytest.raises(RuntimeError, match="refusing insecure"):
        SecretStore(tmp_path / "secrets.json", backend=None).set("key", "value")


def test_backup_manifest_integrity_and_restore(tmp_path: Path):
    root = tmp_path / "source"
    root.mkdir()
    database = root / "memory.db"
    database.write_bytes(b"local data")
    archive = tmp_path / "backup.zip"
    manager = BackupManager(root)
    manager.create(archive, [database])
    manifest = manager.validate(archive)
    assert manifest["format"] == 1
    restored = manager.restore(archive, tmp_path / "restored")
    assert restored["files"][0]["path"] == "memory.db"
    assert (tmp_path / "restored" / "memory.db").read_bytes() == b"local data"


def test_backup_rejects_env_files(tmp_path: Path):
    root = tmp_path / "source"
    root.mkdir()
    env_file = root / ".env"
    env_file.write_text("API_KEY=secret", encoding="utf-8")
    with pytest.raises(ValueError, match="excluded"):
        BackupManager(root).create(tmp_path / "backup.zip", [env_file])
