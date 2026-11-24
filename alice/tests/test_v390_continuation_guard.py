from alice.evolution.continuation_guard import decide_continuation
def test_completed_task_stops(): assert decide_continuation(False,True).action=='complete'
def test_safe_unblocked_continues(): assert decide_continuation(True,True,True).action=='continue'
def test_missing_decision_blocks(): assert decide_continuation(True,False,True).action=='await_missing_decision'
