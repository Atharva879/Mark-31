from __future__ import annotations

import pytest

from interactive_browser import InteractiveBrowser


class FakeLocator:
    def __init__(self, calls):
        self.calls = calls

    def click(self, **kwargs):
        self.calls.append(("click", kwargs))

    def fill(self, text, **kwargs):
        self.calls.append(("fill", text, kwargs))

    def press(self, key, **kwargs):
        self.calls.append(("press", key, kwargs))


class FakePage:
    url = "https://example.com/"

    def __init__(self):
        self.calls = []

    def goto(self, url, **kwargs):
        self.url = url
        self.calls.append(("goto", url, kwargs))

    def title(self):
        return "Example"

    def locator(self, selector):
        self.calls.append(("locator", selector))
        return FakeLocator(self.calls)


class FakeBrowser:
    def __init__(self):
        self.page = FakePage()
        self.closed = False

    def new_page(self):
        return self.page

    def close(self):
        self.closed = True


def test_interactive_browser_actions_are_bounded():
    browser = FakeBrowser()
    adapter = InteractiveBrowser(browser=browser, execute_check=lambda: True)
    assert adapter.navigate("https://example.com")["title"] == "Example"
    adapter.click("button.submit")
    adapter.fill("input[name=q]", "hello")
    adapter.press("input[name=q]", "Enter")
    assert any(call[0] == "click" for call in browser.page.calls)


def test_interactive_browser_rejects_missing_permission_and_unsafe_inputs():
    adapter = InteractiveBrowser(browser=FakeBrowser(), execute_check=lambda: False)
    with pytest.raises(PermissionError):
        adapter.navigate("https://example.com")
    enabled = InteractiveBrowser(browser=FakeBrowser(), execute_check=lambda: True)
    with pytest.raises(ValueError):
        enabled.navigate("file:///tmp/test")
    with pytest.raises(ValueError):
        enabled.click("javascript:alert(1)")
    with pytest.raises(ValueError):
        enabled.fill("input", "x" * 2001)
