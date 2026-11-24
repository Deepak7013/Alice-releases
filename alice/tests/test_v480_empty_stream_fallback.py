import pytest

from alice.providers.router import ProviderError, Router


def test_empty_local_stream_is_not_reported_as_success_or_sent_to_cloud():
    router = Router()
    router._order = lambda: ["local"]
    calls = []

    def fake_stream(provider, prompt, image_path, max_tokens, cancel_event):
        calls.append(provider)
        return iter(())

    router._stream_openai_compatible = fake_stream
    with pytest.raises(ProviderError, match="returned an empty response"):
        list(router.ask_stream("Explain neural networks briefly.", max_tokens=128))
    assert calls == ["local"]
    assert router.health()["local"]["success"] == 0
