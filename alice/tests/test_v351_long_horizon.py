from alice.cognitive.long_horizon import LongHorizonStore
from alice.cognitive.brain import BrainKernel

def test_goal_survives_restart(tmp_path):
    a=LongHorizonStore(tmp_path); g=a.create('AgroChain','finish the project',milestones=['build','test'],next_actions=['run tests'])
    a.milestone(g['goal_id'],'build','build passed')
    b=LongHorizonStore(tmp_path)
    got=b.get(g['goal_id'])
    assert got['status']=='active' and 'build' in got['completed_milestones'] and 'run tests' in got['next_actions']

def test_goal_failure_is_persistent(tmp_path):
    a=LongHorizonStore(tmp_path); g=a.create('X','x'); a.record_failure(g['goal_id'],'provider 402')
    b=LongHorizonStore(tmp_path); assert 'provider 402' in b.get(g['goal_id'])['failures']

def test_brain_can_resume_related_long_goal(tmp_path):
    store=LongHorizonStore(tmp_path); store.create('AgroChain','continue AgroChain website work',next_actions=['implement dashboard'])
    b=BrainKernel(long_horizon=store)
    s=b.think('continue AgroChain website work')
    assert s.related_long_goals and s.related_long_goals[0]['title']=='AgroChain'
