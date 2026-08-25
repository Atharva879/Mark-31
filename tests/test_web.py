from __future__ import annotations

import pytest

from skills.web import WebClient


class FakeResponse:
    def __init__(self, content: bytes, content_type: str = "text/html"):
        self.content = content
        self.encoding = "utf-8"
        self.headers = {"content-type": content_type}
        self.status_code = 200
        self.text = content.decode("utf-8", errors="replace")

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size=8192):
        for index in range(0, len(self.content), chunk_size):
            yield self.content[index:index + chunk_size]

    def json(self):
        import json
        return json.loads(self.content)


class FakeSession:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def public_resolver(host: str) -> list[str]:
    return ["93.184.216.34"]


def test_web_search_parses_bounded_result_links():
    html = b'''
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fnews">Example title</a>
    <a class="result__snippet">A current result snippet.</a>
    '''
    session = FakeSession(FakeResponse(html))
    client = WebClient(session=session, resolver=public_resolver, max_results=2)

    results = client.search("current data", 1)

    assert results == [{"title": "Example title", "url": "https://example.com/news", "snippet": "A current result snippet."}]
    assert session.calls[0][0] == "https://html.duckduckgo.com/html/"


def test_fetch_web_data_returns_clean_html_text_and_metadata():
    session = FakeSession(FakeResponse(b"<html><script>bad()</script><h1>Live</h1><p>Value 42</p></html>"))
    client = WebClient(session=session, resolver=public_resolver, max_response_bytes=1000)

    payload = client.fetch_url("https://example.com/data", max_chars=100)

    assert payload["content_type"] == "text/html"
    assert "bad()" not in payload["content"]
    assert "Live" in payload["content"]
    assert "Value 42" in payload["content"]
    assert payload["status_code"] == 200


def test_fetch_blocks_private_network_targets():
    client = WebClient(resolver=lambda host: ["127.0.0.1"])
    with pytest.raises(PermissionError, match="Private or local"):
        client.fetch_url("http://localhost:8080/admin")


def test_fetch_rejects_non_text_content_type():
    session = FakeSession(FakeResponse(b"PNG", content_type="image/png"))
    client = WebClient(session=session, resolver=public_resolver)
    with pytest.raises(ValueError, match="Unsupported response"):
        client.fetch_url("https://example.com/image.png")


def test_web_limits_are_validated():
    with pytest.raises(ValueError, match="timeout"):
        WebClient(timeout_seconds=0)
    with pytest.raises(ValueError, match="response limit"):
        WebClient(max_response_bytes=20_000_000)
    client = WebClient(resolver=public_resolver, max_results=2)
    with pytest.raises(ValueError, match="between 1 and 2"):
        client.search("test", 3)


def test_runtime_registers_web_tools_without_provider_keys(tmp_path, monkeypatch):
    from config import Settings
    from main import build_runtime

    monkeypatch.setenv("JARVIS_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("JARVIS_MEMORY_DB", str(tmp_path / "memory.db"))
    _router, _dispatcher, registry = build_runtime(Settings.from_env())

    names = {tool.name for tool in registry.all()}
    assert {"web_search", "fetch_web_data"}.issubset(names)
