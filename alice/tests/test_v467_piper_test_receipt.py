import hashlib
import json
from pathlib import Path

from alice.voice.voice import Voice


def _voice(tmp_path):
    voice = Voice.__new__(Voice)
    voice.root = tmp_path
    voice._piper_config_path = tmp_path / "alice_workspace" / "runtime" / "piper_voice.json"
    return voice


def test_receipt_records_model_and_config_hashes_without_full_paths_or_text(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    model = root / "female.onnx"
    model.write_bytes(b"model bytes for receipt test")
    config = root / "female.onnx.json"
    config.write_text(json.dumps({"audio": {"sample_rate": 22050}}), encoding="utf-8")
    voice = _voice(tmp_path)
    voice._piper_config_path.parent.mkdir(parents=True)
    voice._piper_config_path.write_text(json.dumps({"model_root": str(root), "model_path": "female.onnx"}), encoding="utf-8")
    result = {"ok": True, "mode": "piper_local_test", "provider": "alice_piper_local_neural",
              "local_only": True, "fallback_attempted": False, "duration_ms": 123,
              "error": "", "text": "must never be recorded"}
    assert voice._write_local_piper_test_receipt(result)
    receipt_path = tmp_path / "alice_workspace" / "runtime" / "piper_voice_test_receipt.json"
    data = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert data["model_sha256"] == hashlib.sha256(model.read_bytes()).hexdigest()
    assert data["config_sha256"] == hashlib.sha256(voice._piper_config_path.read_bytes()).hexdigest()
    assert data["model_filename"] == "female.onnx"
    assert data["speech_text_recorded"] is False
    serialized = json.dumps(data)
    assert str(tmp_path) not in serialized
    assert "must never be recorded" not in serialized
    assert data["duration_ms"] == 123


def test_receipt_is_written_even_when_model_config_is_missing(tmp_path):
    voice = _voice(tmp_path)
    result = {"ok": False, "mode": "piper_local_test", "provider": "unavailable",
              "local_only": True, "fallback_attempted": False, "duration_ms": 4,
              "error": "model_missing"}
    assert voice._write_local_piper_test_receipt(result)
    path = tmp_path / "alice_workspace" / "runtime" / "piper_voice_test_receipt.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["ok"] is False and data["error"] == "model_missing"
    assert data["model_sha256"] == ""


def test_receipt_write_failure_is_nonfatal(tmp_path):
    root_file = tmp_path / "not_a_directory"
    root_file.write_text("file", encoding="utf-8")
    voice = Voice.__new__(Voice)
    voice.root = root_file
    assert voice._write_local_piper_test_receipt({"ok": False}) is False


def test_receipt_includes_timestamp_and_platform_metadata(tmp_path):
    voice = _voice(tmp_path)
    assert voice._write_local_piper_test_receipt({"ok": True, "duration_ms": 0})
    path = tmp_path / "alice_workspace" / "runtime" / "piper_voice_test_receipt.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["tested_at_utc"].endswith("+00:00")
    assert data["platform"]
    assert data["python_version"]
