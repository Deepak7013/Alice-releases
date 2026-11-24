from alice.engineering.recovery import assess_recovery
def test_recovery_actions():
 assert assess_recovery(True,True,True).recovery_action=='ready_for_explicit_promotion'
 assert assess_recovery(False,True,False).recovery_action=='rollback_candidate'
 assert assess_recovery(False,False,False).recovery_action=='discard_candidate'
