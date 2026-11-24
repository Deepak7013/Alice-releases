import json
from pathlib import Path

from alice.voice.voice import Voice


def test_fresh_install_defaults_to_confirmed_aria_and_persists_it(tmp_path, monkeypatch):
    monkeypatch.setattr("alice.voice.voice.bootstrap_piper_engine", lambda registry, path: type("R", (), {"loaded": False, "registered": False, "reason": "config_missing"})())
    voice = Voice(root=tmp_path)
    try:
        assert voice._voice_mode == "neural"
        assert voice._neural_voice == "en-US-AriaNeural"
        settings = json.loads((tmp_path / "alice_workspace/runtime/voice.json").read_text(encoding="utf-8"))
        assert settings["mode"] == "neural"
        assert settings["neural_voice"] == "en-US-AriaNeural"
    finally:
        voice._speech_queue.put(None)
        voice._speech_thread.join(timeout=2)


def test_existing_voice_settings_are_not_overwritten(tmp_path, monkeypatch):
    runtime = tmp_path / "alice_workspace/runtime"
    runtime.mkdir(parents=True)
    original = {"voice_name": "my-female-sapi-id", "mode": "sapi", "neural_voice": "", "enabled": True}
    (runtime / "voice.json").write_text(json.dumps(original), encoding="utf-8")
    monkeypatch.setattr("alice.voice.voice.bootstrap_piper_engine", lambda registry, path: type("R", (), {"loaded": False, "registered": False, "reason": "config_missing"})())
    voice = Voice(root=tmp_path)
    try:
        assert voice._voice_mode == "sapi"
        assert voice._selected_name == "my-female-sapi-id"
        assert json.loads((runtime / "voice.json").read_text(encoding="utf-8")) == original
    finally:
        voice._speech_queue.put(None)
        voice._speech_thread.join(timeout=2)


def test_neural_startup_skips_sapi_broker(tmp_path):
    voice = Voice.__new__(Voice)
    voice._voice_mode = "neural"
    voice.neural = type("N", (), {"available": staticmethod(lambda: True)})()
    voice._backend_kind = ""
    voice._backend_ready = False
    voice._last_provider = ""
    voice._last_error = ""
    voice._start_powershell = lambda: (_ for _ in ()).throw(AssertionError("SAPI broker should not start in neural mode"))
    voice._warm_up()
    assert voice._backend_kind == "microsoft_edge_neural"
    assert voice._backend_ready is True
