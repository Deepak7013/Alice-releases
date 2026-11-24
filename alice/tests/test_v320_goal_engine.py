from alice.goals import GoalEngine
import pytest


def _verified_outcome():
    return {"verified": True, "verification_evidence": {
        "observed": True, "unverified_steps": [],
        "verified_actions": [{"tool": "write_file", "postcondition_ok": True,
                               "postcondition_evidence": {"observed": True, "evidence_sha256": "a" * 64}}],
    }}

def test_goal_dependencies_and_completion(tmp_path):
    e=GoalEngine(tmp_path); g=e.create('Build','finish project')
    a=e.add_step(g['id'],'Research'); b=e.add_step(g['id'],'Implement',depends_on=[a['id']])
    assert [x['id'] for x in e.ready_steps(g['id'])]==[a['id']]
    e.start_step(g['id'],a['id']); e.complete_step(g['id'],a['id'],'done',verification=_verified_outcome())
    assert [x['id'] for x in e.ready_steps(g['id'])]==[b['id']]
    e.start_step(g['id'],b['id']); out=e.complete_step(g['id'],b['id'],'all good',verification=_verified_outcome())
    assert out['status']=='completed'


def test_goal_cannot_complete_without_independent_action_evidence(tmp_path):
    e=GoalEngine(tmp_path); g=e.create('X','Y'); s=e.add_step(g['id'],'One')
    e.start_step(g['id'],s['id'])
    with pytest.raises(ValueError,match='independently verified'):
        e.complete_step(g['id'],s['id'],'claimed done')
    assert e.status(g['id'])['goal']['status']=='active'
    assert e.get_step(g['id'],s['id'])['status']=='running'


def test_goal_cannot_complete_dependency_out_of_order_even_with_evidence(tmp_path):
    e=GoalEngine(tmp_path); g=e.create('X','Y')
    first=e.add_step(g['id'],'First'); second=e.add_step(g['id'],'Second',depends_on=[first['id']])
    with pytest.raises(ValueError,match='not ready'):
        e.start_step(g['id'],second['id'])

def test_goal_persistence_pause_resume(tmp_path):
    e=GoalEngine(tmp_path); g=e.create('X','Y'); e.add_step(g['id'],'One'); e.pause(g['id'])
    e2=GoalEngine(tmp_path); assert e2.status(g['id'])['goal']['status']=='paused'; e2.resume(g['id']); assert e2.status(g['id'])['goal']['status']=='active'

def test_unknown_dependency_rejected(tmp_path):
    e=GoalEngine(tmp_path); g=e.create('X','Y')
    try: e.add_step(g['id'],'bad',depends_on=['missing'])
    except ValueError: pass
    else: assert False
