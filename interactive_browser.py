"""Playwright-backed browser actions guarded by the desktop Execute session."""

from __future__ import annotations
from pathlib import Path
from urllib.parse import urlparse


class InteractiveBrowser:
    def __init__(
        self, browser=None, execute_check=None, max_text: int = 2000, allowed_roots=None
    ) -> None:

        self.browser = browser
        self.execute_check = execute_check or (lambda: False)
        self.max_text = max(100, min(int(max_text), 10_000))
        self.allowed_roots = [Path(root).expanduser().resolve() for root in (allowed_roots or [])]
        self.page = None

    def _ready(self):
        if not self.execute_check():
            raise PermissionError("desktop Execute mode is disabled or expired")
        if self.browser is None:
            try:
                from playwright.sync_api import sync_playwright
            except ImportError as exc:
                raise RuntimeError("install Playwright and its browser binaries first") from exc
            playwright = sync_playwright().start()
            self.browser = playwright.chromium.launch(headless=False)
        if self.page is None:
            self.page = self.browser.new_page()
        return self.page

    @staticmethod
    def _url(url: str) -> str:
        parsed = urlparse(str(url).strip())
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
        ):
            raise ValueError(
                "browser URL must be an absolute HTTP(S) URL without embedded credentials"
            )
        return url

    @staticmethod
    def _selector(selector: str) -> str:
        selector = str(selector).strip()
        if not selector or len(selector) > 300 or "javascript:" in selector.lower():
            raise ValueError("invalid browser selector")
        return selector

    def navigate(self, url: str) -> dict[str, object]:
        page = self._ready()
        target = self._url(url)
        page.goto(target, wait_until="domcontentloaded", timeout=15_000)
        return {"url": page.url, "title": page.title(), "mode": "interactive_playwright"}

    def click(self, selector: str) -> dict[str, object]:
        page = self._ready()
        selector = self._selector(selector)
        page.locator(selector).click(timeout=10_000)
        return {"action": "click", "selector": selector}

    def fill(self, selector: str, text: str) -> dict[str, object]:
        page = self._ready()
        selector = self._selector(selector)
        if not isinstance(text, str) or not text or len(text) > self.max_text:
            raise ValueError("browser text is empty or exceeds the configured bound")
        page.locator(selector).fill(text, timeout=10_000)
        return {"action": "fill", "selector": selector, "length": len(text)}

    def upload_file(self, selector: str, path: str) -> dict[str, object]:
        page = self._ready()
        selector = self._selector(selector)
        target = Path(path).expanduser().resolve()
        if not any(target == root or root in target.parents for root in self.allowed_roots):
            raise PermissionError("upload path is outside configured allowed roots")
        if target.suffix.lower() not in {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}:
            raise ValueError("unsupported video upload format")
        if not target.is_file() or target.stat().st_size > 4 * 1024 * 1024 * 1024:
            raise ValueError("video is missing or exceeds the upload size limit")
        page.locator(selector).set_input_files(str(target), timeout=10_000)
        return {
            "action": "upload_file",
            "selector": selector,
            "name": target.name,
            "size_bytes": target.stat().st_size,
        }

    def press(self, selector: str, key: str) -> dict[str, object]:
        page = self._ready()
        selector = self._selector(selector)
        if len(str(key)) > 30 or str(key).lower() in {"f12", "printscreen"}:
            raise ValueError("key is not allowed for interactive browser control")
        page.locator(selector).press(str(key), timeout=10_000)
        return {"action": "press", "selector": selector, "key": str(key)}

    def list_pages(self) -> dict[str, object]:
        self._ready()
        return {
            "pages": [
                {"index": i, "url": page.url, "title": page.title()}
                for i, page in enumerate(self.browser.contexts[0].pages)
            ]
        }

    def select_page(self, index: int) -> dict[str, object]:
        self._ready()
        pages = self.browser.contexts[0].pages
        if not isinstance(index, int) or index < 0 or index >= len(pages):
            raise ValueError("browser page index is unavailable")
        self.page = pages[index]
        return {"index": index, "url": self.page.url, "title": self.page.title()}

    def scroll(self, pixels: int) -> dict[str, object]:
        page = self._ready()
        value = max(-3000, min(int(pixels), 3000))
        page.mouse.wheel(0, value)
        return {"action": "scroll", "pixels": value}

    def page_state(self) -> dict[str, object]:
        page = self._ready()
        text = page.locator("body").inner_text(timeout=10_000)
        return {"url": page.url, "title": page.title(), "text": text[: self.max_text]}

    def close(self) -> dict[str, object]:
        if self.browser is not None:
            self.browser.close()
        self.browser = None
        self.page = None
        return {"closed": True}


__all__ = ["InteractiveBrowser"]
