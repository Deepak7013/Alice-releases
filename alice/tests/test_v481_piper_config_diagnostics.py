import json
from pathlib import Path

from alice.voice.engine_registry import LocalVoiceEngineRegistry
from alice.voice.piper_bootstrap import bootstrap_piper_engine


def test_missing_piper_config_has_specific_safe_diagnostic(tmp_path):
    result = bootstrap_piper_engine(LocalVoiceEngineRegistry(), tmp_path / "missing.json")
    assert not result.loaded and not result.registered
    assert result.reason == "config_unreadable_or_invalid"
    assert result.diagnostic == "config_file_not_found"


def test_invalid_json_has_specific_safe_diagnostic(tmp_path):
    config = tmp_path / "piper_voice.json"
    config.write_text('{bad json', encoding="utf-8")
    result = bootstrap_piper_engine(LocalVoiceEngineRegistry(), config)
    assert not result.loaded and not result.registered
    assert result.reason == "config_unreadable_or_invalid"
    assert result.diagnostic == "config_json_invalid"


def test_valid_json_keeps_existing_validation_contract(tmp_path):
    config = tmp_path / "piper_voice.json"
    config.write_text(json.dumps({"unexpected": True}), encoding="utf-8")
    result = bootstrap_piper_engine(LocalVoiceEngineRegistry(), config)
    assert not result.loaded and not result.registered
    assert result.reason == "config_contains_unknown_fields"
