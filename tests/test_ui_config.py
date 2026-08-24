from __future__ import annotations

from ui_config import write_local_env


def test_api_config_is_saved_locally_without_overwriting_other_settings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("JARVIS_LOG_LEVEL=DEBUG\n", encoding="utf-8")

    write_local_env("gemini-secret", "router-secret", "openrouter,gemini")

    content = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "JARVIS_LOG_LEVEL=DEBUG" in content
    assert "GEMINI_API_KEY=gemini-secret" in content
    assert "OPENROUTER_API_KEY=router-secret" in content
    assert "JARVIS_PROVIDER_ORDER=openrouter,gemini" in content
