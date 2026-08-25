from __future__ import annotations

from pathlib import Path

import pytest

from plugins import PluginCatalog


def test_approved_manifest_is_catalogued(tmp_path: Path):
    catalog = PluginCatalog(tmp_path / "plugins")
    item = catalog.approve(
        {
            "id": "weather_local",
            "name": "Local Weather",
            "version": "1.0",
            "tools": [{"name": "read_weather", "risk": "SAFE"}],
        }
    )
    assert item["approved"] is True
    assert catalog.list()[0]["id"] == "weather_local"


def test_manifest_rejects_invalid_risk_and_code_fields(tmp_path: Path):
    catalog = PluginCatalog(tmp_path / "plugins")
    with pytest.raises(ValueError, match="risk"):
        catalog.approve(
            {
                "id": "bad_plugin",
                "name": "Bad",
                "version": "1",
                "entrypoint": "evil.py",
                "tools": [{"name": "run", "risk": "EXECUTE"}],
            }
        )
