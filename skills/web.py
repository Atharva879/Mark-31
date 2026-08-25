"""Bounded public web search and real-time URL retrieval for Jarvis."""

from __future__ import annotations

import ipaddress
import json
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests


@dataclass(frozen=True)
class WebResult:
    title: str
    url: str
    snippet: str

    def as_dict(self) -> dict[str, str]:
        return {"title": self.title, "url": self.url, "snippet": self.snippet}


class _DuckDuckGoParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[WebResult] = []
        self._current_url = ""
        self._current_title: list[str] = []
        self._current_snippet: list[str] = []
        self._capture: str | None = None
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            self._current_url = _clean_result_url(attributes.get("href") or "")
            self._current_title = []
            self._capture = "title"
            self._depth = 1
        elif "result__snippet" in classes:
            self._current_snippet = []
            self._capture = "snippet"
            self._depth = 1
        elif self._capture:
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if not self._capture:
            return
        self._depth -= 1
        if self._depth > 0:
            return
        if self._capture == "snippet" and self._current_url and self._current_title:
            self.results.append(
                WebResult(
                    " ".join("".join(self._current_title).split()),
                    self._current_url,
                    " ".join("".join(self._current_snippet).split()),
                )
            )
            self._current_url = ""
            self._current_title = []
            self._current_snippet = []
        self._capture = None

    def handle_data(self, data: str) -> None:
        if self._capture == "title":
            self._current_title.append(data)
        elif self._capture == "snippet":
            self._current_snippet.append(data)


class WebClient:
    def __init__(
        self,
        timeout_seconds: float = 15.0,
        max_response_bytes: int = 1_000_000,
        max_results: int = 5,
        allowed_hosts: set[str] | None = None,
        session: requests.Session | None = None,
        resolver: Callable[[str], list[str]] | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Web timeout must be greater than zero")
        if max_response_bytes <= 0 or max_response_bytes > 10_000_000:
            raise ValueError("Web response limit must be between 1 and 10,000,000 bytes")
        if max_results <= 0 or max_results > 20:
            raise ValueError("Web result count must be between 1 and 20")
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.max_results = max_results
        self.allowed_hosts = {host.lower().strip() for host in (allowed_hosts or set()) if host.strip()}
        self.session = session or requests.Session()
        self.resolver = resolver or self._resolve
        self.headers = {"User-Agent": "Jarvis/0.1 (+local safety-first assistant)"}

    def search(self, query: str, max_results: int | None = None) -> list[dict[str, str]]:
        query = " ".join(query.split())
        if not query:
            raise ValueError("Search query cannot be empty")
        limit = max_results or self.max_results
        if limit <= 0 or limit > self.max_results:
            raise ValueError(f"Search result count must be between 1 and {self.max_results}")

        response = self.session.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers=self.headers,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        body = response.content[: self.max_response_bytes]
        parser = _DuckDuckGoParser()
        parser.feed(body.decode(response.encoding or "utf-8", errors="replace"))
        if parser.results:
            return [result.as_dict() for result in parser.results[:limit]]

        # The Instant Answer endpoint is a useful fallback for factual queries.
        instant = self.session.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            headers=self.headers,
            timeout=self.timeout_seconds,
        )
        instant.raise_for_status()
        payload = instant.json()
        fallback = _instant_answer_results(payload)
        return fallback[:limit]

    def fetch_url(self, url: str, max_chars: int = 12_000) -> dict[str, Any]:
        normalized = self._validate_url(url)
        if max_chars <= 0 or max_chars > 100_000:
            raise ValueError("Fetched text limit must be between 1 and 100,000 characters")
        response = self.session.get(
            normalized,
            headers={**self.headers, "Accept": "text/html,application/json,text/plain,application/xml;q=0.9"},
            timeout=self.timeout_seconds,
            stream=True,
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "application/octet-stream").split(";", 1)[0].lower()
        if content_type not in {"text/html", "text/plain", "application/json", "application/xml", "text/xml"}:
            raise ValueError(f"Unsupported response content type: {content_type}")
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=8192):
            if not chunk:
                continue
            remaining = self.max_response_bytes - total
            if remaining <= 0:
                break
            piece = chunk[:remaining]
            chunks.append(piece)
            total += len(piece)
            if len(piece) < len(chunk):
                break
        raw = b"".join(chunks)
        encoding = response.encoding or "utf-8"
        text = raw.decode(encoding, errors="replace")
        if content_type == "text/html":
            text = _html_to_text(text)
        elif content_type == "application/json":
            try:
                text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                pass
        return {
            "url": normalized,
            "status_code": response.status_code,
            "content_type": content_type,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "truncated": len(raw) >= self.max_response_bytes or len(text) > max_chars,
            "content": text[:max_chars],
        }

    def _validate_url(self, url: str) -> str:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Only absolute HTTP(S) URLs are supported")
        host = parsed.hostname.lower().rstrip(".")
        if self.allowed_hosts and host not in self.allowed_hosts:
            raise PermissionError("URL host is not allowlisted")
        for address in self.resolver(host):
            ip = ipaddress.ip_address(address)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise PermissionError("Private or local network URLs are blocked")
        return parsed.geturl()

    @staticmethod
    def _resolve(host: str) -> list[str]:
        try:
            return list({item[4][0] for item in socket.getaddrinfo(host, None)})
        except socket.gaierror as exc:
            raise ValueError("URL host could not be resolved") from exc


def _clean_result_url(href: str) -> str:
    parsed = urlparse(href)
    if parsed.hostname and parsed.hostname.endswith("duckduckgo.com") and parsed.path == "/l/":
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(target)
    return href


def _instant_answer_results(payload: dict[str, Any]) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    abstract = payload.get("AbstractText")
    abstract_url = payload.get("AbstractURL")
    heading = payload.get("Heading") or "DuckDuckGo Instant Answer"
    if abstract and abstract_url:
        results.append({"title": str(heading), "url": str(abstract_url), "snippet": str(abstract)})
    for item in payload.get("RelatedTopics", []):
        if isinstance(item, dict) and item.get("Text") and item.get("FirstURL"):
            results.append({"title": str(item["Text"])[:160], "url": str(item["FirstURL"]), "snippet": str(item["Text"])})
    return results


def _html_to_text(value: str) -> str:
    class TextParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.parts: list[str] = []
            self.skip = 0

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag in {"script", "style", "noscript", "svg"}:
                self.skip += 1

        def handle_endtag(self, tag: str) -> None:
            if tag in {"script", "style", "noscript", "svg"} and self.skip:
                self.skip -= 1

        def handle_data(self, data: str) -> None:
            if not self.skip:
                self.parts.append(data)

    parser = TextParser()
    parser.feed(value)
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


__all__ = ["WebClient", "WebResult"]
