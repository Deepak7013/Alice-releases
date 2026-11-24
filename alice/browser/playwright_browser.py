"""Persistent, stateful browser controller for Alice."""
from pathlib import Path
import json
from urllib.parse import urlsplit
from .postconditions import _url_key

class BrowserAgent:
    def __init__(self, profile_dir="data/browser_profile"):
        self.pw = self.context = self.page = None
        self.profile_dir = Path(profile_dir)

    def _existing_session_is_usable(self):
        """Return true only when the cached page belongs to a live context.

        Playwright objects can remain truthy after a tab, context, or browser has
        crashed. Checking only ``self.page`` made every later operation reuse a
        dead session forever. This check is deliberately observational: it never
        retries the operation that failed or repeats a possible side effect.
        """
        if self.page is None or self.context is None:
            return False
        try:
            is_closed = getattr(self.page, "is_closed", None)
            if callable(is_closed) and is_closed():
                return False
            pages = self.context.pages
            return any(page is self.page for page in pages)
        except Exception:
            return False

    def _ensure(self):
        if self._existing_session_is_usable():
            return

        # Retire stale handles before attempting a fresh persistent context. Clear
        # instance state first so a cleanup exception cannot leave a dead session
        # looking usable on the next call.
        old_context, old_pw = self.context, self.pw
        self.pw = self.context = self.page = None
        if old_context is not None or old_pw is not None:
            self._shutdown(old_context, old_pw)

        from playwright.sync_api import sync_playwright
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        pw = context = None
        try:
            pw = sync_playwright().start()
            context = pw.chromium.launch_persistent_context(
                str(self.profile_dir), headless=False, viewport={"width": 1440, "height": 900}
            )
            page = context.pages[0] if context.pages else context.new_page()
        except Exception:
            self._shutdown(context, pw)
            raise
        self.pw, self.context, self.page = pw, context, page

    def recover(self):
        """Re-establish the persistent browser session and return a safe snapshot.

        This does not replay navigation, clicks, form submissions, or keypresses.
        It only restores a usable session and reports the newly observed state.
        """
        self._ensure()
        return {"ok": True, "recovered": True, **self.snapshot()}

    @staticmethod
    def _shutdown(context, pw):
        error = None
        for resource, method in ((context, "close"), (pw, "stop")):
            if resource is None:
                continue
            try:
                getattr(resource, method)()
            except Exception as exc:
                if error is None:
                    error = exc
        if error is not None:
            raise error

    def tabs(self):
        self._ensure()
        return [{"index": i, "url": p.url, "title": p.title()} for i, p in enumerate(self.context.pages)]

    def switch_tab(self, index=0):
        self._ensure(); pages = self.context.pages
        if index < 0 or index >= len(pages): raise IndexError("Invalid browser tab")
        self.page = pages[index]; self.page.bring_to_front()
        return {"ok": True, "url": self.page.url, "title": self.page.title()}

    def open(self, url):
        self._ensure(); self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return {"ok": True, "url": self.page.url, "title": self.page.title()}

    def new_tab(self, url="about:blank"):
        self._ensure(); before_count=len(self.context.pages); self.page = self.context.new_page(); self.page.goto(url, wait_until="domcontentloaded")
        return {"ok": True, "url": self.page.url, "title": self.page.title(),
                "_postcondition_context":{"before_tab_count":before_count,"new_tab_index":len(self.context.pages)-1}}

    @staticmethod
    def _click_expectation(expected_url, expected_text):
        has_url = isinstance(expected_url, str) and bool(expected_url.strip())
        has_text = isinstance(expected_text, str) and bool(expected_text.strip())
        if has_url == has_text:
            raise ValueError("Provide exactly one expected_url or expected_text state change")
        if has_url:
            parsed = urlsplit(expected_url.strip())
            if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
                raise ValueError("expected_url must be an absolute HTTP(S) URL")
            return "url", expected_url.strip()
        if len(expected_text) > 256:
            raise ValueError("expected_text is limited to 256 characters")
        return "text", expected_text

    def _transition_context(self, expected_url, expected_text):
        kind, expected = self._click_expectation(expected_url, expected_text)
        self._ensure()
        before_url = str(self.page.url)
        before_text = str(self.page.locator("body").inner_text(timeout=10000))
        if kind == "url" and _url_key(before_url) == _url_key(expected):
            raise ValueError("expected_url must differ from the current browser URL")
        if kind == "text":
            if len(before_text) > 12000:
                raise ValueError("current page text is too large to establish a safe click baseline")
            if expected in before_text:
                raise ValueError("expected_text must not already be visible before the click")
        return kind, expected, before_url

    @staticmethod
    def _unique(locator):
        count = locator.count()
        if count != 1:
            raise ValueError("Browser click target must match exactly one element")
        return locator

    def click_text(self, text, expected_url=None, expected_text=None):
        kind, _expected, before_url = self._transition_context(expected_url, expected_text)
        locator = self._unique(self.page.get_by_text(text, exact=True))
        locator.click(timeout=10000)
        return {"ok": True, "url": self.page.url,
                "_postcondition_context": {"kind": kind, "before_url": before_url,
                                           "expected_text_absent_before": True}}

    def click_role(self, role, name, expected_url=None, expected_text=None):
        kind, _expected, before_url = self._transition_context(expected_url, expected_text)
        locator = self._unique(self.page.get_by_role(role, name=name, exact=True))
        locator.click(timeout=10000)
        return {"ok": True, "url": self.page.url,
                "_postcondition_context": {"kind": kind, "before_url": before_url,
                                           "expected_text_absent_before": True}}

    def press(self, key, expected_url=None, expected_text=None):
        kind, _expected, before_url = self._transition_context(expected_url, expected_text)
        focused = self.page.locator(":focus")
        if focused.count() != 1:
            raise ValueError("Browser keypress requires exactly one focused target")
        tag = str(focused.evaluate("element => element.tagName")).upper()
        if tag in {"BODY", "HTML"}:
            raise ValueError("Browser keypress requires a focused interactive element")
        self.page.keyboard.press(key)
        return {"ok": True, "url": self.page.url,
                "_postcondition_context": {"kind": kind, "before_url": before_url,
                                           "expected_text_absent_before": True}}

    def fill(self, label, text):
        self._ensure(); self.page.get_by_label(label, exact=False).first.fill(text); return {"ok": True}

    def read_labeled_input(self, label):
        """Independently reread a labeled input value from the active page DOM."""
        self._ensure()
        return self.page.get_by_label(label, exact=False).first.input_value(timeout=10000)

    def page_text(self, max_chars=12000):
        self._ensure(); text = self.page.locator("body").inner_text(timeout=10000)
        return {"ok": True, "text": text[:max_chars], "url": self.page.url, "title": self.page.title()}

    def snapshot(self):
        self._ensure()
        return {"ok": True, "url": self.page.url, "title": self.page.title(), "tabs": self.tabs()}

    def screenshot(self, path="data/workspace/browser.png"):
        self._ensure(); Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=path); return {"ok": True, "path": str(Path(path).resolve()), "url": self.page.url}

    def close(self):
        context, pw = self.context, self.pw
        # Clear instance state before shutdown so callers can safely retry even
        # when Playwright raises while closing a crashed browser/context.
        self.pw = self.context = self.page = None
        self.browser = None
        self._shutdown(context, pw)
