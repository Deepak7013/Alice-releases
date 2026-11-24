import threading

from alice.providers.router import Router


def test_cancelled_before_stream_does_not_resolve_provider_or_issue_request(monkeypatch):
    router = Router()
    calls = []
    monkeypatch.setattr(router, "_order", lambda: calls.append("order") or ["local"])
    monkeypatch.setattr(router, "_stream_openai_compatible", lambda *a, **k: calls.append("request") or iter(["unexpected"]))
    cancelled = threading.Event()
    cancelled.set()

    assert list(router.ask_stream("hello", cancel_event=cancelled)) == []
    assert calls == []


def test_cancelled_before_fast_stream_does_not_probe_or_fallback(monkeypatch):
    router = Router()
    calls = []
    monkeypatch.setattr(router, "local_status", lambda: calls.append("status") or {"reachable": True})
    monkeypatch.setattr(router, "ask_stream", lambda *a, **k: calls.append("fallback") or iter(["unexpected"]))
    cancelled = threading.Event()
    cancelled.set()

    assert list(router.ask_fast_stream("hello", cancel_event=cancelled)) == []
    assert calls == []


def test_cancelled_before_openai_compatible_stream_does_not_construct_client(monkeypatch):
    router = Router()
    calls = []
    monkeypatch.setattr(router, "_openai_client", lambda *a, **k: calls.append("client"))
    cancelled = threading.Event()
    cancelled.set()

    assert list(router._stream_openai_compatible("local", "hello", cancel_event=cancelled)) == []
    assert calls == []
