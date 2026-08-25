"""Windows DPAPI-backed secret storage; never falls back to plaintext."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path


class SecretStore:
    def __init__(self, path: Path, backend=None) -> None:
        self.path = Path(path)
        self.backend = backend if backend is not None else self._load_backend()

    @staticmethod
    def _load_backend():
        if os.name != "nt":
            return None
        try:
            import win32crypt  # type: ignore
        except ImportError:
            return None
        return win32crypt

    def _require_backend(self):
        if self.backend is None:
            raise RuntimeError("Windows DPAPI is unavailable; refusing insecure secret storage")
        return self.backend

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or any(
                not isinstance(v, str) for v in payload.values()
            ):
                raise ValueError("invalid secret store")
            return payload
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("secret store is unreadable") from exc

    def set(self, name: str, value: str) -> None:
        if not name or not isinstance(value, str):
            raise ValueError("secret name and string value are required")
        backend = self._require_backend()
        payload = self._read()
        encrypted = backend.CryptProtectData(
            value.encode("utf-8"), "Mark-31 secret", None, None, None, 0
        )[1]
        payload[name] = base64.b64encode(encrypted).decode("ascii")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    def get(self, name: str) -> str | None:
        backend = self._require_backend()
        encoded = self._read().get(name)
        if encoded is None:
            return None
        try:
            encrypted = base64.b64decode(encoded, validate=True)
            return backend.CryptUnprotectData(encrypted, None, None, None, 0)[1].decode("utf-8")
        except Exception as exc:
            raise RuntimeError("secret could not be decrypted") from exc

    def delete(self, name: str) -> bool:
        self._require_backend()
        payload = self._read()
        if name not in payload:
            return False
        del payload[name]
        self.path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        return True


__all__ = ["SecretStore"]
