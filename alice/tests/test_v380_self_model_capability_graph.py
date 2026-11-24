import json
from alice.capabilities.manager import (
    CapabilityManager, STATUS_AVAILABLE, STATUS_DEGRADED, STATUS_UNAVAILABLE, STATUS_UNVERIFIED
)


def test_capability_graph_loads_legacy_records(tmp_path):
    p = tmp_path / 'alice_workspace'
    p.mkdir()
    (p / 'capabilities.json').write_text(json.dumps({
        'legacy': {'name':'legacy','description':'old','kind':'builtin','source':'alice','enabled':True,'learned_at':1.0}
    }), encoding='utf-8')
    m = CapabilityManager(tmp_path)
    assert m.get('legacy')['status'] == STATUS_UNVERIFIED
    assert not m.has('legacy')


def test_success_failure_and_verified_claims(tmp_path):
    m = CapabilityManager(tmp_path)
    m.register('demo', 'demo capability', alternatives=['computer_control'], dependencies=['python'])
    assert m.status('demo')['status'] == STATUS_UNVERIFIED
    assert not m.can_claim('demo')
    ok = m.record_success('demo', note='smoke test passed')
    assert ok['status'] == STATUS_AVAILABLE
    assert ok['verified'] is True
    assert m.has('demo')
    assert m.can_claim('demo')
    bad = m.record_failure('demo', 'provider unavailable')
    assert bad['status'] == STATUS_DEGRADED
    assert bad['failure_count'] == 1
    assert bad['last_error'] == 'provider unavailable'


def test_self_model_exposes_unverified_and_available(tmp_path):
    m = CapabilityManager(tmp_path)
    m.register('a', 'a')
    m.register('b', 'b')
    m.record_success('b')
    model = m.self_model()
    assert 'a' in model['unverified']
    assert 'b' in model['available']


def test_alternatives_only_returns_operational_capabilities(tmp_path):
    m = CapabilityManager(tmp_path)
    m.register('primary', 'primary', alternatives=['backup'])
    m.register('backup', 'backup')
    assert m.alternatives_for('primary') == []
    m.record_success('backup')
    assert m.alternatives_for('primary') == ['backup']


def test_unavailable_state_is_not_reported_as_has(tmp_path):
    m = CapabilityManager(tmp_path)
    m.register('demo', 'demo')
    m.set_status('demo', STATUS_UNAVAILABLE, configured=False, verified=False, note='missing dependency')
    assert not m.has('demo')
    assert m.status('demo')['configured'] is False
