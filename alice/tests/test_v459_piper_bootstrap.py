import json
import shutil
from pathlib import Path

from alice.voice.engine_registry import LocalVoiceEngineRegistry
from alice.voice.piper_bootstrap import bootstrap_piper_engine


def _ready_config(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    model_root = config_dir / "models"
    model_root.mkdir()
    (model_root / "voice.onnx").write_bytes(b"model")
    (model_root / "voice.onnx.json").write_text(json.dumps({"audio": {"sample_rate": 22050}}), encoding="utf-8")
    exe = tmp_path / "piper.exe"
    exe.write_bytes(b"executable placeholder")
    monkeypatch.setattr(shutil, "which", lambda name: str(exe) if name == "piper" else None)
    cfg = config_dir / "piper.json"
    cfg.write_text(json.dumps({"model_root": "models", "model_path": "voice.onnx", "config_path": "voice.onnx.json"}), encoding="utf-8")
    return cfg


def test_bootstrap_registers_ready_local_engine(tmp_path, monkeypatch):
    cfg = _ready_config(tmp_path, monkeypatch)
    registry = LocalVoiceEngineRegistry()
    result = bootstrap_piper_engine(registry, cfg)
    assert result.loaded and result.registered
    assert result.reason == "local_piper_engine_registered"
    assert registry.available() == ("alice_piper_local_neural",)
    assert registry.select() is result.engine


def test_bootstrap_rejects_unknown_fields_without_mutating_registry(tmp_path, monkeypatch):
    cfg = _ready_config(tmp_path, monkeypatch)
    data = json.loads(cfg.read_text())
    data["download_model_automatically"] = True
    cfg.write_text(json.dumps(data), encoding="utf-8")
    registry = LocalVoiceEngineRegistry()
    result = bootstrap_piper_engine(registry, cfg)
    assert not result.registered and result.reason == "config_contains_unknown_fields"
    assert registry.available() == ()


def test_bootstrap_rejects_missing_model_without_mutating_registry(tmp_path, monkeypatch):
    cfg = _ready_config(tmp_path, monkeypatch)
    data = json.loads(cfg.read_text())
    data["model_path"] = "missing.onnx"
    cfg.write_text(json.dumps(data), encoding="utf-8")
    registry = LocalVoiceEngineRegistry()
    result = bootstrap_piper_engine(registry, cfg)
    assert result.loaded and not result.registered
    assert result.reason == "local_model_or_executable_not_ready"
    assert registry.available() == ()


def test_bootstrap_rejects_oversized_config(tmp_path, monkeypatch):
    cfg = _ready_config(tmp_path, monkeypatch)
    cfg.write_text(" " * (16 * 1024 + 1), encoding="utf-8")
    result = bootstrap_piper_engine(LocalVoiceEngineRegistry(), cfg)
    assert not result.loaded and result.reason == "config_missing_or_too_large"


def test_bootstrap_rejects_non_object_config(tmp_path):
    cfg = tmp_path / "piper.json"
    cfg.write_text("[]", encoding="utf-8")
    result = bootstrap_piper_engine(LocalVoiceEngineRegistry(), cfg)
    assert not result.loaded and result.reason == "config_must_be_object"
