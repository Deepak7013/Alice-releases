import pytest
from alice.cognitive.long_horizon import LongHorizonStore
from alice.cognitive.continuity import ExecutiveContinuity
from alice.cognitive.brain import BrainKernel

def test_resume_returns_persistent_next_action(tmp_path):
    g=LongHorizonStore(tmp_path); x=g.create('Project X','finish X',milestones=['build'],next_actions=['run tests'])
    d=ExecutiveContinuity(g).resume('continue Project X')
    assert d.goal['goal_id']==x['goal_id'] and d.next_action=='run tests'

def test_completion_requires_verified_milestones(tmp_path):
    g=LongHorizonStore(tmp_path); x=g.create('X','x',milestones=['build'])
    c=ExecutiveContinuity(g)
    with pytest.raises(ValueError): c.complete_goal(x['goal_id'],evidence='claim only')
    g.milestone(x['goal_id'],'build','test evidence')
    done=c.complete_goal(x['goal_id'],evidence='verified full test')
    assert done['status']=='completed'

def test_outcome_requires_evidence(tmp_path):
    g=LongHorizonStore(tmp_path); x=g.create('X','x'); c=ExecutiveContinuity(g)
    with pytest.raises(ValueError): c.record_verified_outcome(x['goal_id'],outcome='done',success=True,evidence='')

def test_brain_exposes_next_long_action(tmp_path):
    g=LongHorizonStore(tmp_path); g.create('AgroChain','continue AgroChain development',next_actions=['implement dashboard'])
    b=BrainKernel(long_horizon=g); s=b.think('continue AgroChain development')
    assert s.next_long_action=='implement dashboard'
