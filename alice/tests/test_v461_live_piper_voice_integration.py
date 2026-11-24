from types import SimpleNamespace
import threading

import pytest

from alice.voice.voice import Voice


class FakeRouter:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def speak(self, text):
        self.calls.append(text)
        return self.result


def _voice(mode="piper"):
    voice = Voice.__new__(Voice)
    voice._voice_mode = mode
    voice._neural_voice = ""
    voice._selected_name = ""
    voice._speech_generation = 0
    voice._speech_generation_lock = threading.Lock()
    voice._active_speech_cancel = threading.Event()
    voice._spoken_count = 0
    voice._failure_count = 0
    voice._last_provider = ""
    voice._last_error = ""
    voice._backend_kind = ""
    voice._backend_ready = False
    voice._piper_config_path = None
    return voice


def test_piper_mode_routes_canonical_text_through_local_router():
    voice = _voice()
    voice._local_voice_router = FakeRouter(SimpleNamespace(
        spoken=True, provider="alice_piper_local_neural", reason="local_speech_played"
    ))
    assert voice._speak_with_recovery("Canonical response") is True
    assert voice._local_voice_router.calls == ["Canonical response"]
    assert voice._last_provider == "alice_piper_local_neural"
    assert voice._spoken_count == 1 and voice._failure_count == 0


def test_piper_mode_reports_router_failure_without_claiming_speech():
    voice = _voice()
    voice._local_voice_router = FakeRouter(SimpleNamespace(
        spoken=False, provider="sapi_fallback", reason="no_verified_female_sapi_fallback"
    ))
    assert voice._speak_with_recovery("Hello") is False
    assert voice._last_error == "no_verified_female_sapi_fallback"
    assert voice._spoken_count == 0 and voice._failure_count == 1


def test_female_sapi_fallback_rejects_unknown_or_male_voice():
    voice = _voice()
    voice.list_voices = lambda: [{"id": "male-id", "name": "David", "gender": "Male"}]
    voice._speak_powershell = lambda text: pytest.fail("must not use an unverified/male voice")
    voice._speak_pyttsx3 = lambda *args, **kwargs: pytest.fail("must not use an unverified/male voice")
    assert voice._speak_sapi_female_fallback("Hello") is False
    assert voice._last_error == "no_verified_female_sapi_fallback"


def test_female_sapi_fallback_selects_detected_female_voice_before_playback():
    voice = _voice()
    voice._piper_config_path = None
    voice.list_voices = lambda: [
        {"id": "male-id", "name": "David", "gender": "Male"},
        {"id": "female-id", "name": "Zira", "gender": "Female"},
    ]
    voice._save = lambda: None
    voice._close_powershell = lambda: None
    calls = []
    voice._speak_powershell = lambda text: calls.append((voice._selected_name, text)) or True
    assert voice._speak_sapi_female_fallback("Hello") is True
    assert voice._selected_name == "female-id"
    assert calls == [("female-id", "Hello")]
    assert "female" in voice._last_provider and "fallback" in voice._last_provider


def test_edge_neural_failure_uses_only_verified_female_fallback():
    voice = _voice(mode="neural")
    voice._neural_voice = "en-US-AriaNeural"
    voice._speak_neural = lambda text: False
    calls = []
    voice._speak_sapi_female_fallback = lambda text: calls.append(text) or True
    assert voice._speak_with_recovery("Hello") is True
    assert calls == ["Hello"]
    assert "female" in voice._last_provider and "fallback" in voice._last_provider


def test_piper_selection_fails_closed_when_engine_is_not_ready():
    voice = _voice(mode="sapi")
    voice.local_piper_status = lambda **kwargs: {"ready": False, "reason": "local_model_or_executable_not_ready"}
    with pytest.raises(RuntimeError, match="not ready"):
        voice.select_local_piper()
    assert voice._voice_mode == "sapi"


def test_piper_selection_is_explicit_and_persists_mode():
    voice = _voice(mode="sapi")
    voice.local_piper_status = lambda **kwargs: {"ready": True, "female_profile": True,
                                                  "reason": "local_piper_engine_registered",
                                                  "engines": ["alice_piper_local_neural"]}
    voice.stop = lambda: None
    saved = []
    voice._save = lambda: saved.append(voice._voice_mode)
    selected = voice.select_local_piper()
    assert voice._voice_mode == "piper"
    assert selected["mode"] == "piper"
    assert saved == ["piper"]


def test_piper_status_does_not_activate_it_implicitly():
    voice = _voice(mode="sapi")
    voice._piper_bootstrap_result = SimpleNamespace(loaded=False, registered=False, reason="config_missing")
    voice._is_configured_piper_female = lambda: False
    class Registry:
        def available(self):
            return ()
    voice._local_voice_registry = Registry()
    status = voice.local_piper_status()
    assert not status["ready"] and not status["active"]
    assert voice._voice_mode == "sapi"


def test_piper_status_requires_explicit_female_profile_even_if_engine_registered():
    voice = _voice(mode="sapi")
    voice._piper_bootstrap_result = SimpleNamespace(loaded=True, registered=True, reason="local_piper_engine_registered")
    voice._is_configured_piper_female = lambda: False
    class Registry:
        def available(self):
            return ("alice_piper_local_neural",)
    voice._local_voice_registry = Registry()
    status = voice.local_piper_status()
    assert status["registered"] and not status["ready"]
    assert status["reason"] == "female_profile_not_confirmed_in_config"


def test_piper_status_marks_explicit_female_profile_ready():
    voice = _voice(mode="sapi")
    voice._piper_bootstrap_result = SimpleNamespace(loaded=True, registered=True, reason="local_piper_engine_registered")
    voice._is_configured_piper_female = lambda: True
    class Registry:
        def available(self):
            return ("alice_piper_local_neural",)
    voice._local_voice_registry = Registry()
    status = voice.local_piper_status()
    assert status["ready"] and status["female_profile"]
