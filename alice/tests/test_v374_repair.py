from types import SimpleNamespace
from alice.engineering.repair import RepairController

def test_repair_is_bounded_and_can_recover():
    state={'n':0}
    def validate(): return SimpleNamespace(verified=state['n']>=2)
    def repair(i,_): state['n']+=1; return True
    r=RepairController(3).run(validate,repair)
    assert r.verified and r.iterations==3

def test_repair_limit_stops():
    r=RepairController(1).run(lambda:SimpleNamespace(verified=False),lambda i,x:True)
    assert not r.verified and r.stopped_reason=='repair_limit_reached'
