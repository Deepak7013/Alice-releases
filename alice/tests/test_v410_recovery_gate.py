from alice.execution.recovery_gate import RecoveryGate

def test_verified_success_stops_recovery():
    r=RecoveryGate().decide(verification_ok=True,recoverable=True,attempts_used=0,max_attempts=3)
    assert not r.recover and r.reason=="verified_success"

def test_nonrecoverable_failure_stops():
    r=RecoveryGate().decide(verification_ok=False,recoverable=False,attempts_used=0,max_attempts=3)
    assert not r.recover and r.reason=="not_recoverable"

def test_authority_missing_stops():
    r=RecoveryGate().decide(verification_ok=False,recoverable=True,attempts_used=0,max_attempts=3,authority_available=False)
    assert not r.recover and r.reason=="authority_unavailable"

def test_budget_allows_bounded_retry():
    r=RecoveryGate().decide(verification_ok=False,recoverable=True,attempts_used=1,max_attempts=3)
    assert r.recover and r.next_attempt==2

def test_budget_exhaustion_stops():
    r=RecoveryGate().decide(verification_ok=False,recoverable=True,attempts_used=3,max_attempts=3)
    assert not r.recover and r.reason=="recovery_budget_exhausted"

def test_invalid_budget_stops():
    r=RecoveryGate().decide(verification_ok=False,recoverable=True,attempts_used=-1,max_attempts=3)
    assert not r.recover and r.reason=="invalid_budget"
