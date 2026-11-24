from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from alice.voice import piper_setup


def _args(tmp_path, config_file=None, overwrite=False):
    root = tmp_path / "models"
    root.mkdir(exist_ok=True)
    (root / "voice.onnx").write_bytes(b"local model")
    (root / "voice.onnx.json").write_text(json.dumps({"audio": {"sample_rate": 22050}}), encoding="utf-8")
    exe = tmp_path / "piper.exe"
    exe.write_bytes(b"executable placeholder")
    return dict(config_file=config_file or tmp_path / "runtime" / "piper_voice.json", model_root=root,
                model_path="voice.onnx", model_config_path="voice.onnx.json", executable=str(exe),
                confirm_female_profile=True, overwrite=overwrite)


def test_setup_uses_production_admission_and_reports_ready(tmp_path):
    result = piper_setup.prepare_piper_config(**_args(tmp_path))
    assert result["engine_ready"] is True
    assert result["admission_reason"] == "local_piper_engine_registered"


def test_failed_admission_removes_new_config(tmp_path, monkeypatch):
    monkeypatch.setattr(piper_setup, "bootstrap_piper_engine",
                        lambda registry, path: SimpleNamespace(registered=False, reason="forced_admission_failure"))
    args = _args(tmp_path)
    with pytest.raises(ValueError, match="alice_piper_admission_failed:forced_admission_failure"):
        piper_setup.prepare_piper_config(**args)
    assert not Path(args["config_file"]).exists()


def test_failed_overwrite_restores_original_config_bytes(tmp_path, monkeypatch):
    config = tmp_path / "runtime" / "piper_voice.json"
    config.parent.mkdir()
    original = b'{"existing":"must be preserved"}\n'
    config.write_bytes(original)
    monkeypatch.setattr(piper_setup, "bootstrap_piper_engine",
                        lambda registry, path: SimpleNamespace(registered=False, reason="forced_admission_failure"))
    args = _args(tmp_path, config_file=config, overwrite=True)
    with pytest.raises(ValueError, match="alice_piper_admission_failed"):
        piper_setup.prepare_piper_config(**args)
    assert config.read_bytes() == original
