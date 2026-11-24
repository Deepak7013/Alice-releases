import json
from pathlib import Path
from alice.voice.piper_bootstrap import bootstrap_piper_engine
from alice.voice.engine_registry import LocalVoiceEngineRegistry

def test_missing_config_is_specific_and_does_not_register(tmp_path):
    result = bootstrap_piper_engine(LocalVoiceEngineRegistry(), tmp_path / "missing.json")
    assert result.reason == "config_unreadable_or_invalid"
    assert result.diagnostic == "config_file_not_found"
    assert result.registered is False

def test_malformed_json_is_specific_and_does_not_register(tmp_path):
    cfg = tmp_path / "piper_voice.json"
    cfg.write_text("{not-json", encoding="utf-8")
    result = bootstrap_piper_engine(LocalVoiceEngineRegistry(), cfg)
    assert result.reason == "config_unreadable_or_invalid"
    assert result.diagnostic == "config_json_invalid"
    assert result.registered is False

def test_non_utf8_config_is_specific_and_does_not_register(tmp_path):
    cfg = tmp_path / "piper_voice.json"
    cfg.write_bytes(b"\xff\xfe\xfa")
    result = bootstrap_piper_engine(LocalVoiceEngineRegistry(), cfg)
    assert result.reason == "config_unreadable_or_invalid"
    assert result.diagnostic == "config_not_utf8"
    assert result.registered is False

def test_config_file_size_limit_is_enforced(tmp_path):
    cfg = tmp_path / "piper_voice.json"
    cfg.write_text(" " * 16385, encoding="utf-8")
    result = bootstrap_piper_engine(LocalVoiceEngineRegistry(), cfg)
    assert result.reason == "config_missing_or_too_large"
    assert result.diagnostic == "config_exceeds_size_limit"
    assert result.registered is False
