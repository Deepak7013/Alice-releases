from types import SimpleNamespace
from pathlib import Path
import json

from alice.voice.voice import Voice


class Engine:
    name = "test_piper_local"
    def __init__(self, outcome=True, error=""):
        self.outcome = outcome
        self.last_error = error
        self.calls = []
    def speak(self, text):
        self.calls.append(text)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class Registry:
    def __init__(self, engine): self.engine = engine
    def select(self): return self.engine


def _voice(engine, ready=True, tmp_path=None):
    voice = Voice.__new__(Voice)
    voice.root = tmp_path or Path(".")
    voice._piper_config_path = voice.root / "alice_workspace" / "runtime" / "piper_voice.json"
    voice.local_piper_status = lambda refresh=False: {"ready": ready, "reason": "test_not_ready"}
    voice._local_voice_registry = Registry(engine)
    voice._spoken_count = 0
    voice._failure_count = 0
    voice._last_provider = ""
    voice._last_error = ""
    return voice


def test_local_test_uses_engine_directly_and_reports_no_fallback(tmp_path):
    engine = Engine(True)
    voice = _voice(engine, tmp_path=tmp_path)
    result = voice.test_local_piper_voice("PRIVATE TEST SPEECH MUST NOT BE STORED")
    assert result["ok"] and result["local_only"] and not result["fallback_attempted"]
    assert result["provider"] == "test_piper_local"
    assert engine.calls == ["PRIVATE TEST SPEECH MUST NOT BE STORED"]
    assert voice._spoken_count == 1
    receipt = json.loads((tmp_path / "alice_workspace" / "runtime" / "piper_voice_test_receipt.json").read_text(encoding="utf-8"))
    assert receipt["ok"] is True and receipt["fallback_attempted"] is False
    assert receipt["speech_text_recorded"] is False
    assert "PRIVATE TEST SPEECH MUST NOT BE STORED" not in json.dumps(receipt)
    assert receipt["duration_ms"] >= 0


def test_local_test_failure_is_not_masked_by_sapi_fallback(tmp_path):
    engine = Engine(False, "audio_playback_failed")
    voice = _voice(engine, tmp_path=tmp_path)
    result = voice.test_local_piper_voice("hello local")
    assert not result["ok"]
    assert result["error"] == "audio_playback_failed"
    assert not result["fallback_attempted"]
    assert voice._failure_count == 1


def test_local_test_engine_exception_is_reported_without_fallback(tmp_path):
    voice = _voice(Engine(RuntimeError("fake synthesis error")), tmp_path=tmp_path)
    result = voice.test_local_piper_voice()
    assert not result["ok"]
    assert result["error"] == "fake synthesis error"
    assert result["fallback_attempted"] is False


def test_local_test_does_not_call_engine_if_config_not_ready(tmp_path):
    engine = Engine(True)
    voice = _voice(engine, ready=False, tmp_path=tmp_path)
    result = voice.test_local_piper_voice()
    assert not result["ok"]
    assert result["error"] == "test_not_ready"
    assert engine.calls == []
    assert result["fallback_attempted"] is False


def test_local_test_handles_missing_admitted_engine(tmp_path):
    voice = _voice(Engine(True), tmp_path=tmp_path)
    voice._local_voice_registry = SimpleNamespace(select=lambda: None)
    result = voice.test_local_piper_voice()
    assert not result["ok"]
    assert result["error"] == "local_piper_engine_not_admitted"


def test_local_test_handles_empty_input_as_engine_failure_without_fallback(tmp_path):
    engine = Engine(False, "local_synthesis_or_playback_failed")
    voice = _voice(engine, tmp_path=tmp_path)
    result = voice.test_local_piper_voice("")
    assert not result["ok"]
    assert engine.calls == [""]
    assert result["fallback_attempted"] is False
