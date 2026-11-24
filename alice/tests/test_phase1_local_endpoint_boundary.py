import pytest

from alice.providers.router import ProviderError, Router


@pytest.mark.parametrize("endpoint", [
    "https://api.example.com/v1",
    "http://192.0.2.10:11434/v1",
    "http://10.0.0.8:11434/v1",
    "http://user:pass@localhost:11434/v1",
    "ftp://localhost:11434/v1",
    "http://localhost:11434/v1?token=secret",
])
def test_local_endpoint_policy_rejects_non_local_or_unsafe_urls(endpoint):
    assert Router._is_loopback_url(endpoint) is False


@pytest.mark.parametrize("endpoint", [
    "http://localhost:11434/v1",
    "http://127.0.0.1:11434/v1",
    "http://[::1]:11434/v1",
])
def test_local_endpoint_policy_accepts_loopback_urls(endpoint):
    assert Router._is_loopback_url(endpoint) is True


def test_local_model_call_rejects_remote_endpoint_before_client_construction(monkeypatch):
    router = Router()
    router.local_base = "https://api.example.com/v1"
    monkeypatch.setattr(router, "_openai_client", lambda *a, **k: (_ for _ in ()).throw(AssertionError("client must not be constructed")))
    with pytest.raises(ProviderError, match="remote model endpoints are disabled"):
        router._ask_local("hello")


def test_generic_openai_compatible_client_allows_public_https_api(monkeypatch):
    router = Router()
    created = {}
    class FakeOpenAI:
        def __init__(self, **kwargs):
            created.update(kwargs)
    import sys, types
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    client = router._openai_client("https://api.example.com/v1", "test-key")
    assert isinstance(client, FakeOpenAI)
    assert created["base_url"] == "https://api.example.com/v1"


def test_local_status_refuses_remote_ollama_host_without_request(monkeypatch):
    router = Router()
    monkeypatch.setenv("OLLAMA_HOST", "https://ollama.example.com:11434")
    def forbidden(*args, **kwargs):
        raise AssertionError("remote endpoint must not be contacted")
    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    status = router.local_status()
    assert status["reachable"] is False
    assert status["model_available"] is False
    assert "loopback" in status["error"]
