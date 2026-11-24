import os


def test_local_ai_requires_explicit_enable(monkeypatch):
    monkeypatch.setenv("ALICE_RUNTIME_MODE", "local_required")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("ALICE_ENABLE_LOCAL_AI", "0")
    monkeypatch.setenv("LOCAL_AI_BASE_URL", "http://localhost:11434/v1")
    from alice.providers.router import Router
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    r = Router()
    assert r.available()["local"] is False
    assert r.primary_provider() is None

    # A running Ollama service must not override an explicit local-AI disable.
    monkeypatch.setattr(r,"local_status",lambda:{"reachable":True,"model_available":True,"models":["llama3.2:latest"]})
    assert r.primary_provider() is None
    assert r._order()==[]


def test_local_ai_can_be_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("ALICE_RUNTIME_MODE", "local_required")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("ALICE_ENABLE_LOCAL_AI", "1")
    monkeypatch.setenv("LOCAL_AI_BASE_URL", "http://localhost:11434/v1")
    from alice.providers.router import Router
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    r = Router()
    monkeypatch.setattr(r,"local_status",lambda:{
        "reachable":True,"model_available":True,"models":["llama3.2:latest"]})
    assert r.available()["local"] is True
    assert r.primary_provider() == "local"


def test_quick_chat_model_setting_is_atomic_validated_and_live(tmp_path,monkeypatch):
    from alice.providers.configuration import save_local_fast_model
    env=tmp_path/".env"
    env.write_text("ALICE_TEST_SETTING=keep\n",encoding="utf-8")
    monkeypatch.delenv("ALICE_LOCAL_FAST_MODEL",raising=False)

    save_local_fast_model(env,"gemma3:270m",["gemma3:270m","llama3.2:latest"])

    assert env.read_text(encoding="utf-8")=="ALICE_TEST_SETTING=keep\nALICE_LOCAL_FAST_MODEL=gemma3:270m\n"
    assert os.environ["ALICE_LOCAL_FAST_MODEL"]=="gemma3:270m"
    import pytest
    with pytest.raises(ValueError,match="not installed"):
        save_local_fast_model(env,"llama3:latest",["gemma3:270m"])
    assert "ALICE_LOCAL_FAST_MODEL=gemma3:270m" in env.read_text(encoding="utf-8")
