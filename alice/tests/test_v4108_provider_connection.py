from types import SimpleNamespace
from pathlib import Path

import pytest


def test_openrouter_connection_requires_a_model_before_network(monkeypatch):
    from alice.providers.router import ProviderError, Router

    key = "secret-test-key"
    monkeypatch.setenv("OPENROUTER_API_KEY", key)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    router = Router(provider="openrouter")
    calls = []
    monkeypatch.setattr(router, "_openai_client", lambda *a, **k: calls.append((a, k)))
    with pytest.raises(ProviderError, match="Enter the OpenRouter API key and model first"):
        router.test_openrouter_connection()
    assert calls == []


def test_openrouter_connection_requires_credentials_before_network(monkeypatch):
    from alice.providers.router import ProviderError, Router

    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-test-key")
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    router = Router(provider="openrouter")
    calls = []
    monkeypatch.setattr(router, "_openai_client", lambda *a, **k: calls.append((a, k)))

    with pytest.raises(ProviderError, match="Enter the OpenRouter API key and model first"):
        router.test_openrouter_connection()
    assert calls == []


def test_openrouter_connection_fails_without_key_before_network(monkeypatch):
    from alice.providers.router import ProviderError, Router

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    router = Router(provider="openrouter")
    monkeypatch.setattr(router, "_openai_client", lambda *a, **k: pytest.fail("network must not be called"))

    with pytest.raises(ProviderError, match="Enter the OpenRouter API key and model first"):
        router.test_openrouter_connection()


def test_text_only_openai_compatible_request_uses_plain_string_content(monkeypatch):
    from alice.providers.router import Router

    class Completions:
        kwargs = None
        def create(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="answer"))])
    completions = Completions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    router = Router()
    monkeypatch.setattr(router, "_openai_client", lambda *a, **k: client)

    answer = router._chat(client, router.local_model, "plain user question")

    assert answer == "answer"
    assert completions.kwargs["messages"][0]["content"] == "plain user question"


def test_text_only_local_stream_uses_plain_string_content(monkeypatch):
    from alice.providers.router import Router

    class Stream:
        def __iter__(self):
            return iter([SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="answer"))])])
        def close(self):
            pass
    class Completions:
        kwargs = None
        def create(self, **kwargs):
            self.kwargs = kwargs
            return Stream()
    completions = Completions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    router = Router()
    monkeypatch.setattr(router, "_openai_client", lambda *a, **k: client)
    assert "".join(router._stream_openai_compatible("local", "plain user question")) == "answer"
    assert completions.kwargs["messages"][0]["content"] == "plain user question"


def test_provider_setup_describes_local_only_model_readiness():
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "ui" / "app.py"
    text = source.read_text(encoding="utf-8")
    assert "ALICE Brain · Gemini primary" in text
    assert "Primary model installed" in text


def test_jarvis_local_whisper_is_selectable_and_saved_without_cloud_consent():
    from alice.voice.input import MicrophoneManager

    manager = MicrophoneManager.__new__(MicrophoneManager)
    manager.settings = {}
    manager._lock = __import__("threading").RLock()
    manager._save = lambda: None
    manager.save_input_preferences(input_mode="jarvis_advanced", recognition_backend="local_whisper",
                                   allow_cloud_stt=False)
    assert manager.settings["recognition_backend"] == "local_whisper"
    assert manager.settings["allow_cloud_stt"] is False
    source = Path(__file__).resolve().parents[1] / "ui" / "app.py"
    assert "Local Whisper (offline)" in source.read_text(encoding="utf-8")


def test_window_title_reads_combined_candidate_version():
    from alice.ui.app import AliceUI

    version_file = Path(__file__).resolve().parents[2] / "VERSION.txt"
    expected_version = version_file.read_text(encoding="utf-8").strip().replace("ALICE ", "")
    assert AliceUI._app_version() == expected_version


def test_goal_dialog_exposes_two_labeled_native_fields_and_cleanup():
    source = Path(__file__).resolve().parents[1] / "ui" / "app.py"
    text = source.read_text(encoding="utf-8")
    dialog = text[text.index("    def _create_goal_dialog"):text.index("    def _add_goal_step_dialog")]
    assert 'accessible_label="Goal title:"' in dialog
    assert 'accessible_label="Goal objective:"' in dialog
    assert "native.close()" in dialog
    assert "def save_goal()" in dialog
