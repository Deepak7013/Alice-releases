from types import SimpleNamespace
import threading

from alice.voice.voice import Voice


def _voice(mode):
    voice = Voice.__new__(Voice)
    voice._voice_mode = mode
    voice._neural_voice = "en-US-AriaNeural" if mode == "neural" else ""
    voice.neural = SimpleNamespace(available=lambda: True)
    voice._female_sapi_available = False
    voice._backend_ready = False
    voice._spoken_count = 3
    voice._failure_count = 1
    voice._last_error = ""
    voice._last_provider = ""
    voice._powershell_available = lambda: True
    voice.local_piper_status = lambda: {"ready": False, "engines": [], "reason": "config_missing"}
    return voice


def test_piper_status_does_not_claim_sapi_availability_means_piper_ready():
    voice = _voice("piper")
    status = voice.provider_status()
    assert not status["ready"]
    assert status["provider"] == "unavailable"
    assert status["mode"] == "piper"


def test_piper_status_reports_only_confirmed_female_sapi_fallback():
    voice = _voice("piper")
    voice._female_sapi_available = True
    status = voice.provider_status()
    assert status["ready"]
    assert status["provider"] == "female_sapi_fallback"
    assert status["female_sapi_fallback_available"]


def test_piper_status_prefers_admitted_local_engine():
    voice = _voice("piper")
    voice.local_piper_status = lambda: {"ready": True, "engines": ["alice_piper_local_neural"]}
    status = voice.provider_status()
    assert status["ready"]
    assert status["provider"] == "alice_piper_local_neural"


def test_edge_neural_status_does_not_use_sapi_as_silent_fallback():
    voice = _voice("neural")
    voice._female_sapi_available = True
    status = voice.provider_status()
    assert status["ready"]
    assert status["provider"] == "microsoft_edge_neural"
    voice.neural = SimpleNamespace(available=lambda: False)
    status = voice.provider_status()
    assert not status["ready"] and status["provider"] == "unavailable"


def test_voice_worker_starts_after_required_state_is_initialized(tmp_path, monkeypatch):
    import alice.voice.voice as voice_module
    started = []

    class RecordingThread:
        def __init__(self, target, **kwargs):
            self.target = target
            self.kwargs = kwargs
        def start(self):
            owner = self.target.__self__
            required = ("_last_error", "_last_provider", "_backend_ready", "_female_sapi_available",
                        "_ps_lock", "_active_speech_cancel")
            started.append(all(hasattr(owner, name) for name in required))

    monkeypatch.setattr(voice_module, "threading", SimpleNamespace(
        Thread=RecordingThread, Lock=threading.Lock, RLock=threading.RLock, Event=threading.Event
    ))
    voice = Voice(root=tmp_path)
    assert started == [True]
    assert voice._speech_thread.kwargs["name"] == "AliceVoice"
