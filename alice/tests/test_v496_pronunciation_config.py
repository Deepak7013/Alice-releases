import json
from pathlib import Path
from alice.voice.text_prep import load_pronunciation_dictionary, apply_pronunciation
from alice.voice.voice import Voice


def test_loads_direct_and_wrapped_data_only_maps(tmp_path):
    path = tmp_path / 'pronunciation.json'
    path.write_text(json.dumps({'pronunciations': {'OpenAI': 'Open A I', 'API': 'A P I'}}), encoding='utf-8')
    mapping = load_pronunciation_dictionary(path)
    assert mapping == {'OpenAI': 'Open A I', 'API': 'A P I'}
    assert apply_pronunciation('Use OpenAI API.', mapping) == 'Use Open A I A P I.'


def test_invalid_or_non_object_config_fails_closed(tmp_path):
    path = tmp_path / 'pronunciation.json'
    path.write_text('{broken', encoding='utf-8')
    assert load_pronunciation_dictionary(path) == {}
    path.write_text('[]', encoding='utf-8')
    assert load_pronunciation_dictionary(path) == {}


def test_ignores_oversized_and_non_string_entries(tmp_path):
    path = tmp_path / 'pronunciation.json'
    payload = {'Good': 'Good pronunciation', '': 'empty key', 'TooLong': 'x' * 201, 4: 'number key'}
    path.write_text(json.dumps(payload), encoding='utf-8')
    assert load_pronunciation_dictionary(path) == {'Good': 'Good pronunciation', '4': 'number key'}


def test_voice_loader_uses_runtime_config_without_instantiating_worker(tmp_path):
    v = Voice.__new__(Voice)
    v.root = tmp_path
    cfg = tmp_path / 'alice_workspace' / 'runtime' / 'pronunciation.json'
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({'ALICE': 'A L I C E'}), encoding='utf-8')
    assert v._load_pronunciation_dictionary() == {'ALICE': 'A L I C E'}
