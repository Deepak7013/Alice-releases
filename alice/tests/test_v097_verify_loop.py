from alice.execution.verify_loop import VerifiedExecutor,Verification
from alice.actions.engine import ActionEngine
from alice.actions.store import ActionStore

def test_verification_succeeds(tmp_path):
    e=VerifiedExecutor(ActionEngine(ActionStore(tmp_path)))
    n={'x':0}
    r=e.run('change setting',lambda:(n.__setitem__('x',1) or {'x':1}),lambda x:Verification(x['x']==1,x,'ok'),approval=True)
    assert r.status=='verified' and r.attempts==1

def test_no_approval_means_no_execution(tmp_path):
    n={'x':0}; e=VerifiedExecutor(ActionEngine(ActionStore(tmp_path)))
    r=e.run('send message',lambda:n.__setitem__('x',1),lambda x:True,approval=False)
    assert r.status=='awaiting_approval' and n['x']==0
