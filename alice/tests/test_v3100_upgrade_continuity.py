from alice.deployment.upgrade_continuity import evaluate
def test_continue(): assert evaluate('ALICE v3.100.0','ALICE v3.99.0',receipt_bound=True,health_passed=True,unfinished=True).continuation_allowed
def test_health_blocks(): assert not evaluate('ALICE v3.100.0','ALICE v3.99.0',receipt_bound=True,health_passed=False,unfinished=True).continuation_allowed
def test_receipt_blocks(): assert not evaluate('ALICE v3.100.0','ALICE v3.99.0',receipt_bound=False,health_passed=True,unfinished=True).continuation_allowed
def test_complete_stops(): assert not evaluate('ALICE v3.100.0','ALICE v3.99.0',receipt_bound=True,health_passed=True,unfinished=False).continuation_allowed
def test_blocked_waits(): assert not evaluate('ALICE v3.100.0','ALICE v3.99.0',receipt_bound=True,health_passed=True,unfinished=True,blocked=True).continuation_allowed
