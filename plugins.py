"""Approved plugin manifest catalog; manifests describe capabilities but never execute code."""

from __future__ import annotations

import json
import re
from pathlib import Path

_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
_RISKS = {"SAFE", "MODERATE", "SENSITIVE"}


class PluginCatalog:
    def __init__(self, manifest_dir: Path) -> None:
        self.manifest_dir = Path(manifest_dir)
        self.manifest_dir.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[dict[str, object]]:
        plugins = []
        for path in sorted(self.manifest_dir.glob("*.json")):
            try:
                item = self._validate(json.loads(path.read_text(encoding="utf-8")))
                item["manifest_path"] = str(path)
                plugins.append(item)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        return plugins

    def approve(self, manifest: dict[str, object]) -> dict[str, object]:
        item = self._validate(manifest)
        path = self.manifest_dir / f"{item['id']}.json"
        path.write_text(json.dumps(item, sort_keys=True, indent=2), encoding="utf-8")
        item["manifest_path"] = str(path)
        return item

    @staticmethod
    def _validate(manifest: object) -> dict[str, object]:
        if not isinstance(manifest, dict):
            raise ValueError("plugin manifest must be an object")
        plugin_id = manifest.get("id")
        name = manifest.get("name")
        version = manifest.get("version")
        tools = manifest.get("tools", [])
        if not isinstance(plugin_id, str) or not _ID.fullmatch(plugin_id):
            raise ValueError("invalid plugin id")
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ValueError("invalid plugin name")
        if not isinstance(version, str) or len(version) > 40:
            raise ValueError("invalid plugin version")
        if not isinstance(tools, list) or len(tools) > 50:
            raise ValueError("invalid plugin tools")
        clean_tools = []
        for tool in tools:
            if (
                not isinstance(tool, dict)
                or not isinstance(tool.get("name"), str)
                or not _ID.fullmatch(tool["name"])
            ):
                raise ValueError("invalid plugin tool name")
            if tool.get("risk") not in _RISKS:
                raise ValueError("plugin tool risk must be SAFE, MODERATE, or SENSITIVE")
            clean_tools.append(
                {
                    "name": tool["name"],
                    "risk": tool["risk"],
                    "description": str(tool.get("description", ""))[:240],
                }
            )
        return {
            "id": plugin_id,
            "name": name.strip(),
            "version": version,
            "tools": clean_tools,
            "approved": True,
        }


__all__ = ["PluginCatalog"]
