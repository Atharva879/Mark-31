from __future__ import annotations

from llm.gemini_client import GeminiClient


class FakeResponse:
    status_code = 200
    text = ""

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": "The screen is clear."}]}}]}


def test_gemini_vision_sends_inline_png_without_persisting_it(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["body"] = kwargs["json"]
        return FakeResponse()

    monkeypatch.setattr("llm.gemini_client.requests.post", fake_post)
    response = GeminiClient("test-key", "vision-model").analyze_image(b"PNG", "What is visible?")

    assert response.content == "The screen is clear."
    part = captured["body"]["contents"][0]["parts"][1]["inline_data"]
    assert part["mime_type"] == "image/png"
    assert part["data"]
    assert "vision-model" in captured["url"]
