import os
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_openrouter_preferences_update_selected_provider_and_keep_existing_key(tmp_path, monkeypatch):
    from alice.providers.configuration import save_openrouter_preferences
    for name in ("OPENROUTER_API_KEY", "OPENROUTER_MODEL", "ALICE_PRIMARY_PROVIDER", "ALICE_RUNTIME_MODE", "OPENROUTER_FREE_ONLY"):
        monkeypatch.setenv(name, "")

    env = tmp_path / ".env"
    env.write_text("OPENROUTER_API_KEY=sk-fake\nKEEP_ME=yes\n", encoding="utf-8")
    save_openrouter_preferences(env, "openrouter/auto", free_only=True)
    saved = env.read_text(encoding="utf-8")
    assert "OPENROUTER_API_KEY=sk-fake" in saved
    assert "OPENROUTER_MODEL=openrouter/free" in saved
    assert "ALICE_RUNTIME_MODE=openrouter_primary" in saved


def test_openrouter_preferences_do_not_create_missing_credentials(tmp_path):
    from alice.providers.configuration import save_openrouter_preferences

    env = tmp_path / ".env"
    env.write_text("KEEP_ME=yes\n", encoding="utf-8")
    original = env.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="API key must first be configured"):
        save_openrouter_preferences(env, "openrouter/auto", free_only=True)
    assert env.read_text(encoding="utf-8") == original


def test_openrouter_key_and_free_preference_commit_in_one_update(tmp_path, monkeypatch):
    from alice.providers.configuration import save_openrouter_config
    for name in ("OPENROUTER_API_KEY", "OPENROUTER_MODEL", "ALICE_PRIMARY_PROVIDER", "ALICE_RUNTIME_MODE", "OPENROUTER_FREE_ONLY"):
        monkeypatch.setenv(name, "")

    env = tmp_path / ".env"
    env.write_text("KEEP_ME=yes\n", encoding="utf-8")
    save_openrouter_config(env, "fake-key", "vendor/paid", free_only=True)
    saved = env.read_text(encoding="utf-8")
    assert "OPENROUTER_API_KEY=fake-key" in saved
    assert "OPENROUTER_MODEL=openrouter/free" in saved
    assert "OPENROUTER_FREE_ONLY=true" in saved


def test_local_only_router_never_falls_back_to_hosted_providers(monkeypatch):
    from alice.providers.router import ProviderError, Router

    monkeypatch.setenv("ALICE_RUNTIME_MODE", "local_required")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
    monkeypatch.setenv("OPENROUTER_FREE_ONLY", "true")
    monkeypatch.setenv("OPENROUTER_MODEL", "paid/model")
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(key, "fake-other-key")
    router = Router(provider="auto")
    monkeypatch.setattr(router, "local_enabled", True)
    monkeypatch.setattr(router, "local_status", lambda: {"model_available": True})
    assert router.available()["openrouter"] is True
    assert router._order() == ["local"]
    calls = []
    router._ask_openrouter = lambda *a, **kw: calls.append("openrouter") or (_ for _ in ()).throw(RuntimeError("must remain unused"))
    router._ask_openai = lambda *a, **kw: calls.append("openai") or "paid fallback"
    router._ask_anthropic = lambda *a, **kw: calls.append("anthropic") or "paid fallback"
    router._ask_gemini = lambda *a, **kw: calls.append("gemini") or "paid fallback"
    router._ask_local = lambda *a, **kw: calls.append("local") or (_ for _ in ()).throw(RuntimeError("local unavailable"))
    with pytest.raises(ProviderError):
        router.ask("Explain neural networks briefly.")
    assert calls == ["local"]


def test_local_only_reload_and_streaming_never_use_hosted_provider(monkeypatch):
    from alice.providers.router import ProviderError, Router

    monkeypatch.setenv("ALICE_RUNTIME_MODE", "local_required")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
    monkeypatch.setenv("OPENROUTER_FREE_ONLY", "1")
    monkeypatch.setenv("OPENROUTER_MODEL", "vendor/paid")
    router = Router(provider="openai")
    router.reload_config()
    monkeypatch.setattr(router, "local_enabled", True)
    monkeypatch.setattr(router, "local_status", lambda: {"model_available": True})
    assert router._order() == ["local"]
    calls = []
    def fail(*args, **kwargs):
        calls.append("local")
        raise RuntimeError("local service unavailable")
    router._stream_openai_compatible = fail
    with pytest.raises(ProviderError):
        list(router.ask_stream("Explain neural networks briefly.", allow_fallback=False))
    assert calls == ["local"]


def test_windows_voice_enumeration_falls_back_when_powershell_unavailable(monkeypatch):
    from alice.voice.voice import Voice

    class FakeVoice:
        id = "HKEY_LOCAL_MACHINE\\Zira"
        name = "Microsoft Zira Desktop"
        gender = "Female"

    class FakeEngine:
        def getProperty(self, name):
            assert name == "voices"
            return [FakeVoice()]
        def stop(self):
            pass

    import pyttsx3
    monkeypatch.setattr(Voice, "_powershell_available", staticmethod(lambda: False))
    monkeypatch.setattr(pyttsx3, "init", lambda *args, **kwargs: FakeEngine())
    voices = Voice.list_voices(SimpleNamespace(_powershell_available=lambda: False,
                                                _voice_dict=Voice._voice_dict, _last_error=""))
    assert len(voices) == 1
    assert voices[0]["name"] == "Microsoft Zira Desktop"
    assert Voice._is_female(voices[0])


def test_piper_ui_status_names_missing_configuration_file():
    source = Path(__file__).resolve().parents[1] / "ui" / "app.py"
    text = source.read_text(encoding="utf-8")
    assert 'piper_status.get("diagnostic")' in text


