from alice.deployment.rollback_record import decide_rollback
def test_healthy_retain(): assert decide_rollback(True,True).action=='retain_current'
def test_rollback_requires_approval():
 assert decide_rollback(False,True).action=='await_explicit_rollback_approval'
 assert decide_rollback(False,True,True).action=='rollback'
def test_no_rollback_quarantines(): assert decide_rollback(False,False).action=='quarantine_and_recover'
