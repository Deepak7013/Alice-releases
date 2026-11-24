from types import SimpleNamespace

from alice.voice.engine_registry import LocalVoiceEngineRegistry
from alice.voice.voice import Voice


class ReadyEngine:
    name = "test_old_piper_engine"
    offline = True

    def can_generate(self, text):
        return bool(text)

    def speak(self, text):
        return True


def _voice(tmp_path):
    voice = Voice.__new__(Voice)
    voice.root = tmp_path
    voice._piper_config_path = tmp_path / "alice_workspace" / "runtime" / "piper_voice.json"
    voice._voice_mode = "sapi"
    voice._neural_voice = ""
    old_registry = LocalVoiceEngineRegistry()
    assert old_registry.register(ReadyEngine()).admitted
    voice._local_voice_registry = old_registry
    voice._piper_bootstrap_result = SimpleNamespace(loaded=True, registered=True, reason="old_config_loaded")
    voice._local_voice_router = SimpleNamespace(registry=old_registry)
    voice._is_configured_piper_female = lambda: False
    return voice, old_registry


def test_refresh_replaces_registry_and_discards_stale_engine(tmp_path):
    voice, old_registry = _voice(tmp_path)
    status = voice.local_piper_status(refresh=True)
    assert voice._local_voice_registry is not old_registry
    assert voice._local_voice_router.registry is voice._local_voice_registry
    assert voice._local_voice_registry.available() == ()
    assert not status["ready"] and not status["registered"]
    assert status["reason"] == "config_unreadable_or_invalid"
    assert voice._voice_mode == "sapi"


def test_status_without_refresh_does_not_change_registry(tmp_path):
    voice, old_registry = _voice(tmp_path)
    status = voice.local_piper_status()
    assert voice._local_voice_registry is old_registry
    assert voice._local_voice_router.registry is old_registry
    assert not status["ready"]


def test_explicit_refresh_helper_returns_new_bootstrap_result(tmp_path):
    voice, old_registry = _voice(tmp_path)
    result = voice._refresh_local_piper_config()
    assert not result.loaded and not result.registered
    assert voice._local_voice_registry is not old_registry
    assert voice._piper_bootstrap_result is result
