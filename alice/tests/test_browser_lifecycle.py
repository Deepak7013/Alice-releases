from types import ModuleType
import sys

import pytest

from alice.browser.playwright_browser import BrowserAgent


def _install_playwright(monkeypatch, playwright):
    parent = ModuleType("playwright")
    sync_api = ModuleType("playwright.sync_api")
    sync_api.sync_playwright = lambda: playwright
    monkeypatch.setitem(sys.modules, "playwright", parent)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)


def test_startup_failure_stops_started_playwright(tmp_path, monkeypatch):
    class Chromium:
        def launch_persistent_context(self, *args, **kwargs):
            raise RuntimeError("browser launch failed")
    class Playwright:
        def __init__(self):
            self.chromium = Chromium()
            self.stopped = False
        def start(self): return self
        def stop(self): self.stopped = True

    playwright = Playwright()
    _install_playwright(monkeypatch, playwright)
    agent = BrowserAgent(tmp_path / "profile")
    with pytest.raises(RuntimeError, match="browser launch failed"):
        agent._ensure()
    assert playwright.stopped
    assert agent.pw is agent.context is agent.page is None


def test_close_stops_playwright_and_clears_state_even_if_context_close_fails():
    class Context:
        def close(self): raise RuntimeError("context close failed")
    class Playwright:
        def __init__(self): self.stopped = False
        def stop(self): self.stopped = True

    playwright = Playwright()
    agent = BrowserAgent()
    agent.pw, agent.context, agent.page = playwright, Context(), object()
    with pytest.raises(RuntimeError, match="context close failed"):
        agent.close()
    assert playwright.stopped
    assert agent.pw is agent.context is agent.page is agent.browser is None


def test_close_is_safe_after_partial_or_repeated_lifecycle():
    agent = BrowserAgent()
    agent.close()
    agent.close()


def test_ensure_recreates_session_when_cached_page_is_closed(tmp_path, monkeypatch):
    class Page:
        def __init__(self, url="about:blank", closed=False):
            self.url = url
            self.closed = closed
        def is_closed(self): return self.closed
        def title(self): return "fresh page"
        def bring_to_front(self): pass

    class Context:
        def __init__(self, page): self.pages = [page]; self.closed = False
        def close(self): self.closed = True
        def new_page(self):
            page = Page(); self.pages.append(page); return page

    class Chromium:
        def __init__(self): self.contexts = []
        def launch_persistent_context(self, *args, **kwargs):
            context = Context(Page())
            self.contexts.append(context)
            return context

    class Playwright:
        def __init__(self): self.chromium = Chromium(); self.stopped = False
        def start(self): return self
        def stop(self): self.stopped = True

    old_page = Page("https://stale.invalid", closed=True)
    old_context = Context(old_page)
    old_pw = Playwright()
    _install_playwright(monkeypatch, old_pw)
    agent = BrowserAgent(tmp_path / "profile")
    agent.pw, agent.context, agent.page = old_pw, old_context, old_page

    agent._ensure()

    assert old_context.closed
    assert old_pw.stopped
    assert len(old_pw.chromium.contexts) == 1
    assert agent.context is old_pw.chromium.contexts[0]
    assert agent.page is agent.context.pages[0]
    assert agent.page is not old_page


def test_ensure_recreates_session_when_context_is_unreadable(tmp_path, monkeypatch):
    class DeadContext:
        @property
        def pages(self): raise RuntimeError("context disconnected")
        def close(self): pass

    class Page:
        def is_closed(self): return False

    class NewContext:
        def __init__(self): self.pages = [Page()]
        def close(self): pass

    class Chromium:
        def __init__(self): self.calls = 0; self.context = NewContext()
        def launch_persistent_context(self, *args, **kwargs):
            self.calls += 1
            return self.context

    class Playwright:
        def __init__(self): self.chromium = Chromium(); self.stopped = False
        def start(self): return self
        def stop(self): self.stopped = True

    old_pw = Playwright()
    _install_playwright(monkeypatch, old_pw)
    agent = BrowserAgent(tmp_path / "profile")
    agent.pw, agent.context, agent.page = old_pw, DeadContext(), Page()

    agent._ensure()

    assert old_pw.chromium.calls == 1
    assert agent.context is old_pw.chromium.context
    assert agent.page is agent.context.pages[0]


def test_recover_only_reopens_session_and_reports_observed_snapshot(tmp_path, monkeypatch):
    class Page:
        url = "about:blank"
        def is_closed(self): return False
        def title(self): return "Blank"
        def bring_to_front(self): pass

    class Context:
        def __init__(self): self.pages = [Page()]
        def close(self): pass

    class Chromium:
        def launch_persistent_context(self, *args, **kwargs): return Context()

    class Playwright:
        def __init__(self): self.chromium = Chromium()
        def start(self): return self
        def stop(self): pass

    _install_playwright(monkeypatch, Playwright())
    agent = BrowserAgent(tmp_path / "profile")
    result = agent.recover()

    assert result["ok"] is True
    assert result["recovered"] is True
    assert result["url"] == "about:blank"
    assert result["title"] == "Blank"
    assert len(result["tabs"]) == 1


def test_browser_recovery_postcondition_requires_independent_state_match():
    from alice.browser.postconditions import verify_browser_recover_postcondition

    class Browser:
        def snapshot(self):
            return {"url": "about:blank", "title": "Blank", "tabs": [{"url": "about:blank"}]}

    browser = Browser()
    result = {"ok": True, "recovered": True, "url": "about:blank",
              "title": "Blank", "tabs": [{"url": "about:blank"}]}
    assert verify_browser_recover_postcondition(browser, {}, result).ok

    result["url"] = "https://stale.invalid/"
    outcome = verify_browser_recover_postcondition(browser, {}, result)
    assert not outcome.ok
    assert outcome.evidence["observed"] is True


def test_browser_recovery_postcondition_fails_closed_when_readback_throws():
    from alice.browser.postconditions import verify_browser_recover_postcondition

    class Browser:
        def snapshot(self): raise RuntimeError("browser disconnected")

    result = {"ok": True, "recovered": True, "url": "about:blank",
              "title": "Blank", "tabs": [{"url": "about:blank"}]}
    outcome = verify_browser_recover_postcondition(Browser(), {}, result)
    assert not outcome.ok
    assert outcome.evidence == {"observed": False}
