from pathlib import Path

import pytest


def test_local_only_mode_ignores_configured_hosted_keys(monkeypatch):
    from alice.providers.router import Router
    monkeypatch.setenv("ALICE_RUNTIME_MODE", "local_required")

    monkeypatch.setenv("GROQ_API_KEY", "legacy-groq")
    monkeypatch.setenv("OPENROUTER_API_KEY", "legacy-openrouter")
    monkeypatch.setenv("OPENAI_API_KEY", "legacy-openai")
    monkeypatch.setattr(Router, "_local_service_detected", staticmethod(lambda: False))
    router = Router(provider="openrouter")
    assert router.available()["local"] is False
    assert router.available()["groq"] is True
    assert router.available()["openrouter"] is True
    assert router.primary_provider() is None


def test_router_can_reload_local_model_configuration(monkeypatch):
    from alice.providers.router import Router

    monkeypatch.setenv("LOCAL_AI_MODEL", "llama3.2:latest")
    monkeypatch.setattr(Router, "_local_service_detected", staticmethod(lambda: False))
    router = Router()
    monkeypatch.setenv("LOCAL_AI_MODEL", "qwen2.5:7b")
    state = router.reload_config()
    assert router.local_model == "qwen2.5:7b"
    assert state["openai"] is False


def test_brain_setup_keeps_gemini_and_hosted_config_can_be_saved_explicitly(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "ui" / "app.py"
    text = source.read_text(encoding="utf-8")
    section = text[text.index("    def provider_setup"):text.index("    def build_tools")]
    assert "ALICE Brain · Gemini primary" in section
    assert "GEMINI_API_KEY" in section
    assert 'values=("OpenRouter","Groq")' not in section

    from alice.providers.configuration import save_openrouter_config
    for name in ("OPENROUTER_API_KEY", "OPENROUTER_MODEL", "ALICE_PRIMARY_PROVIDER", "ALICE_RUNTIME_MODE"):
        monkeypatch.setenv(name, "")
    env = tmp_path / ".env"
    original = "ALICE_RUNTIME_MODE=local_required\nOPENROUTER_API_KEY=legacy\n"
    env.write_text(original, encoding="utf-8")
    save_openrouter_config(env, "new-secret")
    saved = env.read_text(encoding="utf-8")
    assert "OPENROUTER_API_KEY=new-secret" in saved
    assert "ALICE_RUNTIME_MODE=openrouter_primary" in saved
    assert "ALICE_RUNTIME_MODE=local_required" not in saved
    assert original != saved
