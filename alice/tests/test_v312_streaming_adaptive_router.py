from types import SimpleNamespace

from alice.providers.router import Router
from alice.agent.agent import AliceAgent


def test_streaming_forwards_max_tokens_and_yields_chunks(monkeypatch):
    monkeypatch.setenv("ALICE_RUNTIME_MODE", "local_required")
    r = Router()
    r._order = lambda: ["local"]
    seen = {}
    def fake_stream(provider, prompt, image_path, max_tokens, cancel_event):
        seen["provider"] = provider
        seen["max_tokens"] = max_tokens
        yield "Hel"
        yield "lo"
    r._stream_openai_compatible = fake_stream
    assert list(r.ask_stream("Explain neural networks briefly.", max_tokens=128)) == ["Hel", "lo"]
    assert seen == {"provider": "local", "max_tokens": 128}
    assert r.health()["local"]["success"] == 1


def test_router_never_selects_hosted_provider_from_health_or_configuration(monkeypatch):
    monkeypatch.setenv("ALICE_RUNTIME_MODE", "local_required")
    r = Router()
    monkeypatch.setattr(r, "local_enabled", True)
    monkeypatch.setattr(r, "local_status", lambda: {"model_available": True})
    r.available = lambda: {"openrouter": True, "openai": True, "local": True, "gemini": True, "anthropic": True}
    r._record_success("openrouter", 1.20)
    r._record_success("openai", 0.20)
    assert r._order() == ["local"]


def test_router_keeps_local_selection_after_hosted_provider_failures(monkeypatch):
    monkeypatch.setenv("ALICE_RUNTIME_MODE", "local_required")
    r = Router()
    monkeypatch.setattr(r, "local_enabled", True)
    monkeypatch.setattr(r, "local_status", lambda: {"model_available": True})
    r._record_success("openrouter", 0.30)
    r._record_failure("openai", RuntimeError("temporary"))
    r._record_failure("openai", RuntimeError("temporary"))
    assert r._order() == ["local"]


def test_anthropic_accepts_router_token_budget():
    import inspect
    assert "max_tokens" in inspect.signature(Router._ask_anthropic).parameters


def test_gemini_accepts_router_token_budget():
    import inspect
    assert "max_tokens" in inspect.signature(Router._ask_gemini).parameters


def test_agent_streaming_uses_router_stream_and_budget(monkeypatch):
    class FakeRouter:
        def __init__(self): self.calls = []
        def ask_stream(self, prompt, image_path=None, allow_fallback=True, max_tokens=None, cancel_event=None):
            self.calls.append(max_tokens)
            yield "A"
            yield "lice"
    r = FakeRouter()
    a = AliceAgent(r, tools=SimpleNamespace())
    assert "".join(a.respond_text_stream("Explain neural networks briefly.", concise=True)) == "Alice"
    assert r.calls == [256]


def test_openai_compatible_stream_uses_stream_flag_and_closes(monkeypatch):
    monkeypatch.setenv("ALICE_RUNTIME_MODE", "local_required")
    class Delta:
        def __init__(self, content): self.content = content
    class Choice:
        def __init__(self, content): self.delta = Delta(content)
    class Chunk:
        def __init__(self, content): self.choices = [Choice(content)]
    class Stream:
        def __init__(self): self.closed = False
        def __iter__(self):
            yield Chunk("A")
            yield Chunk("lice")
        def close(self): self.closed = True
    class Completions:
        def __init__(self): self.kwargs=None; self.stream=Stream()
        def create(self, **kwargs): self.kwargs=kwargs; return self.stream
    class Client:
        def __init__(self): self.chat=SimpleNamespace(completions=Completions())
    r=Router()
    r._order=lambda:["local"]
    client=Client()
    r._openai_client=lambda *args, **kwargs: client
    assert "".join(r.ask_stream("Explain neural networks briefly.", max_tokens=77)) == "Alice"
    assert client.chat.completions.kwargs["stream"] is True
    assert client.chat.completions.kwargs["max_tokens"] == 77
    assert client.chat.completions.stream.closed is True
