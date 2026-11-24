import os
import queue
from types import SimpleNamespace

from alice.agent.agent import AliceAgent
from alice.ui.app import AliceUI


def test_local_router_max_tokens_is_forwarded(monkeypatch):
    from alice.providers.router import Router
    monkeypatch.setenv("ALICE_RUNTIME_MODE", "local_required")
    r = Router()
    calls = {}
    r._order=lambda:["local"]
    r._ask_local=lambda prompt, image_path=None, max_tokens=None: calls.update(max_tokens=max_tokens) or "ok"
    assert r.ask("Please explain neural networks briefly.", max_tokens=256) == "ok"
    assert calls["max_tokens"] == 256


def test_respond_text_uses_short_token_budget(monkeypatch):
    class R:
        def __init__(self): self.max_tokens=None
        def ask(self, prompt, image_path=None, allow_fallback=True, max_tokens=None): self.max_tokens=max_tokens; return "ok"
    r=R(); a=AliceAgent(r, tools=SimpleNamespace())
    assert a.respond_text("Explain neural networks briefly.", concise=True) == "ok"
    assert r.max_tokens == 256


def test_voice_intent_overrides_text_mode():
    assert AliceUI._wants_voice("Explain this with voice")
    assert AliceUI._wants_voice("read it aloud")
    assert AliceUI._wants_voice("tell me verbally")
    assert not AliceUI._wants_voice("Explain this in text")


def test_voice_queue_and_warmup_are_async_api():
    from alice.voice.voice import Voice
    v = Voice.__new__(Voice)
    v._speech_queue=queue.Queue(); v.engine=None; v._lock=__import__('threading').RLock()
    assert hasattr(v, 'speak_async')
    assert callable(v.speak_async)
