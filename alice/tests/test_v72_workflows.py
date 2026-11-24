from alice.orchestration import WorkflowEngine, WorkflowStep, WorkflowStatus

def test_workflow_dependency_order():
    e=WorkflowEngine(); w=e.create('x',[WorkflowStep('b','second',['a']),WorkflowStep('a','first')]); seen=[]
    e.run(w,lambda s: seen.append(s.step_id) or s.step_id)
    assert seen==['a','b'] and w.status==WorkflowStatus.COMPLETED

def test_workflow_failure_stops_dependents():
    e=WorkflowEngine(); w=e.create('x',[WorkflowStep('a','bad'),WorkflowStep('b','later',['a'])])
    e.run(w,lambda s: (_ for _ in ()).throw(RuntimeError('no')))
    assert w.status==WorkflowStatus.FAILED and w.steps[1].status=='pending'

def test_invalid_dependency_rejected():
    e=WorkflowEngine()
    try: e.create('x',[WorkflowStep('a','a',['missing'])]); assert False
    except ValueError: pass
