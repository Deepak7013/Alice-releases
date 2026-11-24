import json
from pathlib import Path
import shutil

import pytest

from alice.voice.piper_setup import prepare_piper_config


def _artifacts(tmp_path):
    root = tmp_path / "models"
    root.mkdir(exist_ok=True)
    (root / "female.onnx").write_bytes(b"model-data")
    (root / "female.onnx.json").write_text(json.dumps({"audio": {"sample_rate": 22050}}), encoding="utf-8")
    exe = tmp_path / "piper.exe"
    exe.write_bytes(b"test executable placeholder")
    return root, exe


def _setup(tmp_path, *, confirm=True, overwrite=False):
    root, exe = _artifacts(tmp_path)
    return prepare_piper_config(config_file=tmp_path / "runtime" / "piper_voice.json", model_root=root,
                                model_path="female.onnx", model_config_path="female.onnx.json",
                                executable=str(exe), confirm_female_profile=confirm, overwrite=overwrite)


def test_setup_writes_strict_config_without_running_executable(tmp_path):
    result = _setup(tmp_path)
    data = json.loads(Path(result["config_file"]).read_text(encoding="utf-8"))
    assert result["written"] and result["female_profile_confirmed"]
    assert data["gender"] == "female"
    assert data["model_path"] == "female.onnx"
    assert Path(data["model_root"]).is_absolute()


def test_female_profile_requires_explicit_confirmation(tmp_path):
    with pytest.raises(ValueError, match="female_voice_profile_confirmation_required"):
        _setup(tmp_path, confirm=False)


def test_existing_config_is_not_overwritten_without_opt_in(tmp_path):
    result = _setup(tmp_path)
    path = Path(result["config_file"])
    before = path.read_bytes()
    with pytest.raises(FileExistsError, match="piper_config_exists"):
        _setup(tmp_path)
    assert path.read_bytes() == before


def test_setup_rejects_path_traversal(tmp_path):
    root, exe = _artifacts(tmp_path)
    with pytest.raises(ValueError, match="safe_relative_path"):
        prepare_piper_config(config_file=tmp_path / "runtime" / "piper_voice.json", model_root=root,
                             model_path="../outside.onnx", model_config_path="female.onnx.json",
                             executable=str(exe), confirm_female_profile=True)


def test_setup_rejects_invalid_model_config_json(tmp_path):
    root, exe = _artifacts(tmp_path)
    (root / "female.onnx.json").write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError, match="valid_json"):
        prepare_piper_config(config_file=tmp_path / "runtime" / "piper_voice.json", model_root=root,
                             model_path="female.onnx", model_config_path="female.onnx.json",
                             executable=str(exe), confirm_female_profile=True)


def test_setup_rejects_missing_executable(tmp_path):
    root, _ = _artifacts(tmp_path)
    with pytest.raises(ValueError, match="executable_not_found"):
        prepare_piper_config(config_file=tmp_path / "runtime" / "piper_voice.json", model_root=root,
                             model_path="female.onnx", model_config_path="female.onnx.json",
                             executable=str(tmp_path / "missing.exe"), confirm_female_profile=True)


def test_setup_rejects_non_model_extension(tmp_path):
    root, exe = _artifacts(tmp_path)
    (root / "not-model.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="extension_not_supported"):
        prepare_piper_config(config_file=tmp_path / "runtime" / "piper_voice.json", model_root=root,
                             model_path="not-model.txt", model_config_path="female.onnx.json",
                             executable=str(exe), confirm_female_profile=True)
