import os
from types import SimpleNamespace

import pytest


def test_gemini_is_default_primary_and_missing_key_fails_clearly(monkeypatch):
    from alice.providers.router import ProviderError, Router

    for name in ("ALICE_RUNTIME_MODE", "GEMINI_API_KEY", "OPENAI_API_KEY",
                 "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(Router, "_local_service_detected", staticmethod(lambda: False))
    router = Router()
    assert router.runtime_policy.mode == "gemini_primary"
    assert router.primary_provider() == "gemini"
    assert router.available()["gemini"] is False
    assert router._order() == ["gemini"]
    with pytest.raises(ProviderError, match="no API key is configured"):
        router.ask("hello")


def test_explicit_local_mode_stays_offline_even_with_gemini_key(monkeypatch):
    from alice.providers.router import Router

    monkeypatch.setenv("ALICE_RUNTIME_MODE", "local_required")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-secret-that-must-not-be-used")
    monkeypatch.setenv("ALICE_ENABLE_LOCAL_AI", "1")
    router = Router()
    monkeypatch.setattr(router, "local_status", lambda: {"model_available": True})
    assert router.primary_provider() == "local"
    assert router._order() == ["local"]


def test_save_gemini_config_preserves_unrelated_values_and_never_returns_key(tmp_path, monkeypatch):
    from alice.providers.configuration import save_gemini_config

    key = "test-local-secret-123456789"
    path = tmp_path / ".env"
    path.write_text("KEEP_ME=existing\nALICE_RUNTIME_MODE=local_required\n", encoding="utf-8")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = save_gemini_config(path, key, "gemini-3.8-flash")
    saved = path.read_text(encoding="utf-8")
    assert result is None
    assert "KEEP_ME=existing" in saved
    assert "GEMINI_API_KEY=" + key in saved
    assert "ALICE_RUNTIME_MODE=gemini_primary" in saved
    assert os.environ["GEMINI_API_KEY"] == key
    with pytest.raises(ValueError):
        save_gemini_config(path, "bad\nkey", "gemini-3.8-flash")


def test_gemini_text_and_stream_use_current_sdk_without_real_network(monkeypatch):
    from google.genai import types
    from alice.providers.router import Router

    monkeypatch.setenv("ALICE_RUNTIME_MODE", "gemini_primary")
    monkeypatch.setenv("GEMINI_API_KEY", "test-secret-not-a-real-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
    calls = []

    class Models:
        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(text="Hello from Gemini")

        def generate_content_stream(self, **kwargs):
            calls.append(kwargs)
            yield SimpleNamespace(text="Hello ")
            yield SimpleNamespace(text="Gemini")

    router = Router()
    router._gemini_client = lambda api_key=None: SimpleNamespace(models=Models())
    assert router.ask("hello", allow_fallback=False) == "Hello from Gemini"
    assert "".join(router.ask_stream("hello", allow_fallback=False)) == "Hello Gemini"
    assert calls[0]["config"].max_output_tokens <= 2048
    assert isinstance(calls[0]["config"], types.GenerateContentConfig)


def test_native_function_call_is_only_a_proposal_and_invalid_call_is_rejected(monkeypatch):
    from alice.providers.router import ProviderError, Router

    monkeypatch.setenv("ALICE_RUNTIME_MODE", "gemini_primary")
    selected = {"read_status": {
        "description": "Read a harmless status value.", "risk": "read",
        "input_schema": {"type": "object", "properties": {"topic": {"type": "string"}},
                         "required": ["topic"], "additionalProperties": False},
    }}
    called = []

    class Models:
        def __init__(self, name):
            self.name = name

        def generate_content(self, **kwargs):
            called.append(kwargs)
            if self.name == "missing_tool":
                parts = [SimpleNamespace(function_call=SimpleNamespace(name="not_registered", args={}))]
            else:
                parts = [SimpleNamespace(function_call=SimpleNamespace(
                    name="read_status", args={"topic": "runtime"}))]
            return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=parts))])

    router = Router()
    router._gemini_client = lambda api_key=None: SimpleNamespace(models=Models("valid"))
    plan = router.ask_plan_with_tools("check status", selected)
    assert plan == {"goal": "", "done": False,
                    "steps": [{"tool": "read_status", "args": {"topic": "runtime"}}]}
    # The provider only proposes a function call; no registry callback is invoked here.
    assert len(called) == 1
    assert called[0]["config"].automatic_function_calling.disable is True

    router._gemini_client = lambda api_key=None: SimpleNamespace(models=Models("missing_tool"))
    with pytest.raises(ProviderError, match="unregistered tool call"):
        router.ask_plan_with_tools("run arbitrary tool", selected)


def test_gemini_failure_diagnostics_do_not_persist_api_secret(monkeypatch):
    from alice.providers.router import ProviderError, Router

    key = "secret-value-should-not-appear"
    monkeypatch.setenv("ALICE_RUNTIME_MODE", "gemini_primary")
    monkeypatch.setenv("GEMINI_API_KEY", key)
    router = Router()
    router._gemini_client = lambda api_key=None: (_ for _ in ()).throw(RuntimeError(key + " invalid"))
    with pytest.raises(ProviderError):
        router.ask("hello")
    assert key not in str(router.health())


@pytest.mark.parametrize("code, expected", [
    (401, "authentication failed"),
    (403, "authentication failed"),
    (404, "HTTP 404"),
    (429, "quota limit"),
    (500, "HTTP 500"),
    (503, "HTTP 503"),
    (504, "HTTP 504"),
])
def test_gemini_http_status_errors_are_actionable_and_secret_safe(code, expected):
    from alice.providers.router import Router

    error = RuntimeError("private provider body containing secret-key-value")
    error.code = code
    result = Router._clean_provider_error("gemini", error)
    assert expected in result
    assert "secret-key-value" not in result


def test_gemini_retries_one_transient_server_error_but_not_other_statuses(monkeypatch):
    from alice.providers.router import ProviderError, Router

    monkeypatch.setenv("ALICE_RUNTIME_MODE", "gemini_primary")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setattr("alice.providers.router.time.sleep", lambda _seconds: None)

    class Models:
        def __init__(self, code):
            self.code = code
            self.calls = 0
        def generate_content(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                error = RuntimeError("temporary server failure")
                error.code = self.code
                raise error
            return SimpleNamespace(text="Recovered")

    models = Models(503)
    router = Router()
    router._gemini_client = lambda api_key=None: SimpleNamespace(models=models)
    assert router.ask("hello", allow_fallback=False) == "Recovered"
    assert models.calls == 2

    rejected = Models(401)
    router._gemini_client = lambda api_key=None: SimpleNamespace(models=rejected)
    with pytest.raises(ProviderError, match="authentication failed"):
        router.ask("hello", allow_fallback=False)
    assert rejected.calls == 1


def test_gemini_stream_retries_only_before_any_text_is_emitted(monkeypatch):
    from alice.providers.router import Router

    monkeypatch.setenv("ALICE_RUNTIME_MODE", "gemini_primary")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setattr("alice.providers.router.time.sleep", lambda _seconds: None)

    class Models:
        calls = 0
        def generate_content_stream(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                error = RuntimeError("temporary gateway failure")
                error.code = 503
                raise error
            yield SimpleNamespace(text="Recovered stream")

    models = Models()
    router = Router()
    router._gemini_client = lambda api_key=None: SimpleNamespace(models=models)
    assert "".join(router.ask_stream("hello", allow_fallback=False)) == "Recovered stream"
    assert models.calls == 2


def test_gemini_api_key_text_is_blocked_before_chat_or_persistence(monkeypatch):
    from alice.ui.app import AliceUI

    secret = "AIzaSy" + "A" * 30

    class Entry:
        def __init__(self):
            self.cleared = False
        def delete(self, *_args):
            self.cleared = True

    ui = object.__new__(AliceUI)
    ui.entry = Entry()
    ui._sync_message_to_native = lambda: None
    shown = []
    ui.say = lambda speaker, text: shown.append((speaker, text))
    ui._submit_text(f"gemini api key={secret}", source="main")

    assert ui.entry.cleared
    assert shown and shown[0][0] == "Alice"
    assert secret not in repr(shown)
    assert "not sent or saved" in shown[0][1]
    assert not hasattr(ui, "_last_request_text")

