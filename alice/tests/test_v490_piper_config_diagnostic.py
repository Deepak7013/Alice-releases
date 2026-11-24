import json
from pathlib import Path
from DIAGNOSE_PIPER_CONFIG import diagnose

def test_missing_config_is_read_only_and_specific(tmp_path):
    assert diagnose(tmp_path / "missing.json")["code"] == "config_file_not_found"

def test_valid_config_reports_missing_model_root(tmp_path):
    cfg=tmp_path / "piper_voice.json"
    cfg.write_text(json.dumps({"model_root":"missing","model_path":"voice.onnx","config_path":"voice.onnx.json"}),encoding="utf-8")
    assert diagnose(cfg)["code"] == "model_root_missing"

def test_rejects_artifact_path_escape(tmp_path):
    root=tmp_path / "models"; root.mkdir()
    cfg=tmp_path / "piper_voice.json"
    cfg.write_text(json.dumps({"model_root":"models","model_path":"../outside.onnx","config_path":"voice.json"}),encoding="utf-8")
    assert diagnose(cfg)["code"] == "configured_artifact_escapes_model_root"

def test_valid_schema_missing_model_file_is_specific(tmp_path):
    root=tmp_path / "models"; root.mkdir()
    cfg=tmp_path / "piper_voice.json"
    cfg.write_text(json.dumps({"model_root":"models","model_path":"voice.onnx","config_path":"voice.onnx.json"}),encoding="utf-8")
    assert diagnose(cfg)["code"] == "model_file_missing"
