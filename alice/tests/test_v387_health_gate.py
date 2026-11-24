from alice.deployment.health_gate import evaluate_health

def test_health_requires_all_invariants():
 assert evaluate_health(True,True,True,True).healthy

def test_health_blocks_on_manifest_failure():
 assert not evaluate_health(True,False,True,True).healthy

def test_health_blocks_on_protected_failure():
 assert not evaluate_health(True,True,True,False).healthy
