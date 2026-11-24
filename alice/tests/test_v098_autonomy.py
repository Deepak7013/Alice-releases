import pytest
from alice.autonomy.bounded import BoundedAutonomy,Budget

def test_budget_bounds_execution():
    n=[]; a=BoundedAutonomy(Budget(max_steps=2))
    assert a.run([lambda:n.append(1),lambda:n.append(2)])==[None,None]
    assert n==[1,2]
    with pytest.raises(RuntimeError): a.run([lambda:n.append(3)])

def test_default_budget_is_finite():
    assert BoundedAutonomy().budget.max_steps==10 and BoundedAutonomy().budget.max_seconds>0

def test_time_budget_is_enforced(monkeypatch):
    clock=[0.0]
    monkeypatch.setattr('alice.autonomy.bounded.time.monotonic',lambda:clock[0])
    a=BoundedAutonomy(Budget(max_steps=5,max_seconds=1.0))
    with pytest.raises(RuntimeError, match='time budget'):
        a.run([lambda:clock.__setitem__(0,2.0), lambda:None])
