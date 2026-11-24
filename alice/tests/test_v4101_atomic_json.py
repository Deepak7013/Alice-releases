import json
from pathlib import Path
import pytest
from alice.core.atomic_json import atomic_write_json


def test_atomic_json_writes_valid_utf8_and_replaces_existing(tmp_path):
    target = tmp_path / "state.json"
    target.write_text('{"old": true}', encoding="utf-8")
    atomic_write_json(target, {"label": "ALICE", "value": "తెలుగు"})
    assert json.loads(target.read_text(encoding="utf-8")) == {"label": "ALICE", "value": "తెలుగు"}
    assert not list(tmp_path.glob("state.json.*.tmp"))


def test_atomic_json_serialization_failure_preserves_previous_file(tmp_path):
    target = tmp_path / "state.json"
    target.write_text('{"preserve": true}', encoding="utf-8")
    with pytest.raises(TypeError):
        atomic_write_json(target, {"bad": object()})
    assert json.loads(target.read_text(encoding="utf-8")) == {"preserve": True}
    assert not list(tmp_path.glob("state.json.*.tmp"))
