import json
import shutil
import subprocess
import wave
from pathlib import Path
from types import SimpleNamespace

from alice.voice.piper_engine import PiperLocalVoiceEngine


def _setup(tmp_path, monkeypatch):
    root = tmp_path / "models"
    root.mkdir()
    (root / "voice.onnx").write_bytes(b"model-placeholder")
    (root / "voice.onnx.json").write_text(json.dumps({"audio": {"sample_rate": 22050}}), encoding="utf-8")
    executable = tmp_path / "piper.exe"
    executable.write_bytes(b"test executable placeholder")
    monkeypatch.setattr(shutil, "which", lambda name: str(executable) if name == "piper" else None)
    return root


def _write_wav(path: Path):
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(22050)
        stream.writeframes(b"\x00\x00" * 256)


def test_piper_engine_reports_ready_for_local_model_files(tmp_path, monkeypatch):
    root = _setup(tmp_path, monkeypatch)
    engine = PiperLocalVoiceEngine(model_root=root, model_path="voice.onnx", config_path="voice.onnx.json")
    assert engine.offline and engine.local_owned and not engine.remote_dependency
    assert engine.can_generate("Hello ALICE")


def test_piper_engine_rejects_path_traversal(tmp_path, monkeypatch):
    root = _setup(tmp_path, monkeypatch)
    engine = PiperLocalVoiceEngine(model_root=root, model_path="../voice.onnx", config_path="voice.onnx.json")
    assert not engine.can_generate("Hello")


def test_piper_engine_rejects_missing_executable(tmp_path, monkeypatch):
    root = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    engine = PiperLocalVoiceEngine(model_root=root, model_path="voice.onnx", config_path="voice.onnx.json")
    assert not engine.can_generate("Hello")


def test_piper_engine_synthesizes_and_plays_valid_wav(tmp_path, monkeypatch):
    root = _setup(tmp_path, monkeypatch)
    played = []
    def runner(args, **kwargs):
        _write_wav(Path(args[args.index("--output_file") + 1]))
        assert kwargs["shell"] is False
        assert kwargs["input"] == "Hello ALICE"
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    engine = PiperLocalVoiceEngine(model_root=root, model_path="voice.onnx", config_path="voice.onnx.json",
                                   cache_dir=tmp_path / "cache", runner=runner,
                                   playback=lambda path: played.append(path.exists()) or True)
    assert engine.speak("Hello ALICE")
    assert played == [True]
    assert list((tmp_path / "cache").glob("*.wav")) == []


def test_piper_engine_rejects_invalid_audio_output(tmp_path, monkeypatch):
    root = _setup(tmp_path, monkeypatch)
    def runner(args, **kwargs):
        Path(args[args.index("--output_file") + 1]).write_bytes(b"not a wav")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    engine = PiperLocalVoiceEngine(model_root=root, model_path="voice.onnx", config_path="voice.onnx.json",
                                   runner=runner, playback=lambda path: True)
    assert not engine.speak("Hello")
    assert engine.last_error == "generated_audio_invalid_or_too_large"


def test_piper_engine_bounds_text_and_audio_settings(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        PiperLocalVoiceEngine(model_root=tmp_path, model_path="m", config_path="c", max_text_chars=0)
    with pytest.raises(ValueError):
        PiperLocalVoiceEngine(model_root=tmp_path, model_path="m", config_path="c", max_audio_bytes=1)


def test_piper_engine_fails_closed_when_playback_fails(tmp_path, monkeypatch):
    root = _setup(tmp_path, monkeypatch)
    def runner(args, **kwargs):
        _write_wav(Path(args[args.index("--output_file") + 1]))
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    engine = PiperLocalVoiceEngine(model_root=root, model_path="voice.onnx", config_path="voice.onnx.json",
                                   runner=runner, playback=lambda path: False)
    assert not engine.speak("Hello")
    assert engine.last_error == "audio_playback_failed"
