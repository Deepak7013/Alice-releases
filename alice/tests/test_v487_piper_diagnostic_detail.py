import json
from pathlib import Path
from alice.voice.piper_bootstrap import bootstrap_piper_engine
from alice.voice.engine_registry import LocalVoiceEngineRegistry


def _boot(tmp_path, payload):
    cfg = tmp_path / 'piper_voice.json'
    cfg.write_text(json.dumps(payload), encoding='utf-8')
    return bootstrap_piper_engine(LocalVoiceEngineRegistry(), cfg)


def test_piper_bootstrap_reports_missing_required_fields_without_echoing_config(tmp_path):
    result = _boot(tmp_path, {'model_root': 'models'})
    assert result.reason == 'config_required_fields_missing'
    assert result.diagnostic == 'config_missing_required_fields'
    assert 'models' not in result.diagnostic


def test_piper_bootstrap_reports_invalid_field_shape_without_values(tmp_path):
    result = _boot(tmp_path, {'model_root': 7, 'model_path': 'model.onnx', 'config_path': 'model.json'})
    assert result.reason == 'config_field_invalid'
    assert result.diagnostic == 'config_required_field_not_nonempty_string'


def test_piper_bootstrap_reports_unknown_fields_without_echoing_them(tmp_path):
    result = _boot(tmp_path, {'model_root': 'models', 'model_path': 'model.onnx', 'config_path': 'model.json', 'secret': 'do-not-log'})
    assert result.reason == 'config_contains_unknown_fields'
    assert result.diagnostic == 'config_has_unsupported_fields'
    assert 'do-not-log' not in result.diagnostic
