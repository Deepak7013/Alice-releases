from pathlib import Path

import pytest


@pytest.mark.parametrize("provider,key_env,model_env", [
    ("openai", "OPENAI_API_KEY", "OPENAI_MODEL"),
    ("anthropic", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"),
    ("groq", "GROQ_API_KEY", "GROQ_MODEL"),
    ("openrouter", "OPENROUTER_API_KEY", "OPENROUTER_MODEL"),
    ("nvidia", "NVIDIA_API_KEY", "NVIDIA_MODEL"),
])
def test_hosted_provider_config_is_explicit_and_secret_is_not_returned(
    tmp_path, monkeypatch, provider, key_env, model_env
):
    from alice.providers.configuration import save_hosted_provider_config
    from alice.providers.router import Router

    for name in ("OPENAI_API_KEY", "OPENAI_MODEL", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
                 "GROQ_API_KEY", "GROQ_MODEL", "OPENROUTER_API_KEY", "OPENROUTER_MODEL",
                 "NVIDIA_API_KEY", "NVIDIA_MODEL", "ALICE_RUNTIME_MODE", "ALICE_PRIMARY_PROVIDER"):
        monkeypatch.setenv(name, "")
    path = tmp_path / ".env"
    monkeypatch.delenv(key_env, raising=False)
    monkeypatch.delenv(model_env, raising=False)
    secret = "private-test-token-123456"
    result = save_hosted_provider_config(path, provider, secret, "test-model")
    assert result is None
    assert key_env + "=" + secret in path.read_text(encoding="utf-8")
    router = Router(provider=provider)
    assert router.primary_provider() == provider
    assert router.available()[provider] is True
    assert router._order() == [provider]


def test_missing_explicit_key_does_not_fall_back_to_another_provider(monkeypatch):
    from alice.providers.router import ProviderError, Router

    for name in ("OPENAI", "ANTHROPIC", "GROQ", "OPENROUTER", "NVIDIA"):
        monkeypatch.delenv(name + "_API_KEY", raising=False)
    monkeypatch.setenv("ALICE_RUNTIME_MODE", "groq_primary")
    monkeypatch.setenv("OPENAI_API_KEY", "other-provider-secret")
    router = Router()
    assert router.primary_provider() == "groq"
    assert router._order() == ["groq"]
    with pytest.raises(ProviderError, match="Groq has no locally configured API key"):
        router._ask_groq("hello")


def test_hosted_credential_savers_replace_only_the_selected_provider(tmp_path, monkeypatch):
    from alice.providers.configuration import save_hosted_provider_config

    for name in ("OPENAI_API_KEY", "OPENAI_MODEL", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
                 "GROQ_API_KEY", "GROQ_MODEL", "OPENROUTER_API_KEY", "OPENROUTER_MODEL",
                 "NVIDIA_API_KEY", "NVIDIA_MODEL", "ALICE_RUNTIME_MODE", "ALICE_PRIMARY_PROVIDER"):
        monkeypatch.setenv(name, "")
    path = tmp_path / ".env"
    path.write_text("UNRELATED=value\nOPENAI_API_KEY=old\n", encoding="utf-8")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    save_hosted_provider_config(path, "groq", "new-groq-secret", "model-id")
    saved = path.read_text(encoding="utf-8")
    assert "UNRELATED=value" in saved
    assert "OPENAI_API_KEY=old" in saved
    assert "GROQ_API_KEY=new-groq-secret" in saved
    assert "ALICE_RUNTIME_MODE=groq_primary" in saved
    assert "ALICE_PRIMARY_PROVIDER=groq" in saved


def test_hosted_connection_restores_environment_and_redacts_key(monkeypatch):
    from alice.providers.router import ProviderError, Router

    key = "private-test-secret-54321"
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    router = Router(provider="groq")
    monkeypatch.setattr(router, "_hosted_chat", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("failed " + key)))
    with pytest.raises(ProviderError) as error:
        router.test_hosted_connection("groq", api_key=key, model="model-id")
    assert key not in str(error.value)
    assert "GROQ_API_KEY" not in __import__("os").environ
    assert "GROQ_MODEL" not in __import__("os").environ


def test_brain_setup_exposes_explicit_hosted_provider_setup():
    root = Path(__file__).resolve().parents[1]
    source = (root / "ui" / "premium_bridge.py").read_text(encoding="utf-8")
    assert "def save_hosted_provider_settings" in source
    assert "def test_hosted_provider_connection" in source
