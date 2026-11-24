from alice.engineering.run_ledger import EngineeringRunLedger

def test_run_ledger_is_deduplicated_and_persistent(tmp_path):
    l=EngineeringRunLedger(tmp_path)
    a=l.record("p1","Improve planner",{"risk":"low"})
    b=l.record("p1","Improve planner",{"risk":"low"})
    assert a["run_id"]==b["run_id"]
    assert len(l.list())==1
    l2=EngineeringRunLedger(tmp_path)
    assert l2.list("p1")[0]["status"]=="preflighted"

def test_run_ledger_does_not_execute_or_change_source(tmp_path):
    target=tmp_path/"source.py"; target.write_text("x=1\n",encoding="utf-8")
    EngineeringRunLedger(tmp_path).record("p2","plan",{"files":["source.py"]})
    assert target.read_text(encoding="utf-8")=="x=1\n"
