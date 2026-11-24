from alice.planning.planner import GoalPlanner
from alice.execution.plan_runner import PlanExecutor

def test_plan_executes_and_records_actions(tmp_path):
    from alice.actions.engine import ActionEngine
    from alice.actions.store import ActionStore
    p=GoalPlanner().plan('research python')
    e=PlanExecutor(ActionEngine(ActionStore(tmp_path)))
    r=e.execute(p,lambda s:{'ok':True,'action':s.action})
    assert r.status=='executed' and len(r.steps)==2

def test_high_risk_waits_for_approval(tmp_path):
    from alice.actions.engine import ActionEngine
    from alice.actions.store import ActionStore
    p=GoalPlanner().plan('send an email')
    e=PlanExecutor(ActionEngine(ActionStore(tmp_path)))
    r=e.execute(p,lambda s:True)
    assert r.status=='awaiting_approval' and r.steps[0].status=='executed' and r.steps[1].status=='awaiting_approval'
