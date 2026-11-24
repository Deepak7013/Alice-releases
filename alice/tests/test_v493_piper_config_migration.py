import json
from pathlib import Path
from MIGRATE_PIPER_CONFIG import migrate


def setup_source(root: Path):
    runtime = root / 'alice_workspace' / 'runtime'
    model_root = runtime / 'models'
    model_root.mkdir(parents=True)
    (model_root / 'voice.onnx').write_bytes(b'model')
    (model_root / 'voice.onnx.json').write_text('{"sample_rate":22050}', encoding='utf-8')
    (runtime / 'piper_voice.json').write_text(json.dumps({
        'model_root': 'models', 'model_path': 'voice.onnx', 'config_path': 'voice.onnx.json',
        'executable': 'piper', 'gender': 'female'
    }), encoding='utf-8')


def test_migration_normalizes_relative_model_root(tmp_path):
    old, new = tmp_path / 'old', tmp_path / 'new'
    setup_source(old)
    result = migrate(old, new)
    assert result['ok']
    saved = json.loads((new / 'alice_workspace/runtime/piper_voice.json').read_text(encoding='utf-8'))
    assert saved['model_root'] == str((old / 'alice_workspace/runtime/models').resolve())
    assert (new / 'alice_workspace/runtime/models').exists() is False


def test_migration_refuses_missing_source_and_preserves_destination(tmp_path):
    old, new = tmp_path / 'old', tmp_path / 'new'
    dest = new / 'alice_workspace/runtime/piper_voice.json'
    dest.parent.mkdir(parents=True)
    dest.write_text('{"keep":true}', encoding='utf-8')
    assert migrate(old, new)['reason'] == 'source_config_missing'
    assert json.loads(dest.read_text()) == {'keep': True}


def test_migration_refuses_unconfirmed_gender(tmp_path):
    old, new = tmp_path / 'old', tmp_path / 'new'
    setup_source(old)
    cfg = old / 'alice_workspace/runtime/piper_voice.json'
    data = json.loads(cfg.read_text()); data['gender'] = 'male'; cfg.write_text(json.dumps(data))
    assert migrate(old, new)['reason'] == 'source_voice_not_confirmed_female'
    assert not (new / 'alice_workspace/runtime/piper_voice.json').exists()


def test_migration_refuses_existing_target_by_default(tmp_path):
    old, new = tmp_path / 'old', tmp_path / 'new'
    setup_source(old)
    dest = new / 'alice_workspace/runtime/piper_voice.json'
    dest.parent.mkdir(parents=True); dest.write_text('{"preserve":true}')
    assert migrate(old, new)['reason'] == 'destination_config_exists_refusing_overwrite'
    assert json.loads(dest.read_text()) == {'preserve': True}


def test_migration_refuses_missing_gender_confirmation(tmp_path):
    old, new = tmp_path / 'old', tmp_path / 'new'
    setup_source(old)
    cfg = old / 'alice_workspace/runtime/piper_voice.json'
    data = json.loads(cfg.read_text()); data.pop('gender'); cfg.write_text(json.dumps(data))
    assert migrate(old, new)['reason'] == 'source_voice_not_confirmed_female'
    assert not (new / 'alice_workspace/runtime/piper_voice.json').exists()
