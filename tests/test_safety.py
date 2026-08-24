from __future__ import annotations

import json

import pytest

from audit import AuditLogger
from config import Settings
from llm.schemas import RiskTier, ToolSpec
from safety import build_confirmation_request, requires_confirmation


def test_invalid_provider_order_is_rejected():
    with pytest.raises(ValueError, match="only gemini and openrouter"):
        Settings.from_env({"JARVIS_PROVIDER_ORDER": "gemini,unknown"})


def test_settings_parse_paths_and_limits():
    result = Settings.from_env(
        {
            "JARVIS_PROVIDER_ORDER": "openrouter,gemini",
            "JARVIS_REQUEST_TIMEOUT_SECONDS": "12.5",
            "JARVIS_MAX_RETRIES_PER_PROVIDER": "2",
            "JARVIS_MAX_TOOL_ROUNDS": "4",
            "JARVIS_MAX_INPUT_CHARS": "1000",
            "JARVIS_ALLOWED_ROOTS": "/tmp/a:/tmp/b",
        }
    )
    assert result.provider_order == ("openrouter", "gemini")
    assert result.request_timeout_seconds == 12.5
    assert result.max_retries_per_provider == 2
    assert result.allowed_roots[0].name == "a"


def test_sensitive_confirmation_is_unconditional():
    spec = ToolSpec(
        name="delete_item",
        description="Delete an item",
        parameters={"type": "object"},
        risk=RiskTier.SENSITIVE,
        handler=lambda: None,
    )
    request = build_confirmation_request(spec, {"target": "x"})
    assert requires_confirmation(spec)
    assert request.risk is RiskTier.SENSITIVE
    assert "x" in request.prompt


def test_audit_redacts_secret_like_values(tmp_path):
    path = tmp_path / "audit.jsonl"
    AuditLogger(path).record("provider_error", message="authorization=secret", token="Bearer abc")
    record = json.loads(path.read_text())
    assert record["message"] == "[REDACTED]"
    assert record["token"] == "[REDACTED]"
