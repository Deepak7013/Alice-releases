from alice.deployment.governed_upgrade import GovernedUpgradeController
def test_governed_upgrade_evaluates_but_never_executes():
 r=GovernedUpgradeController().evaluate({'risk':'low'},'a','a',True,'3.85.0','c',['a.py'],True)
 assert r.verified and r.integrity_ok and r.bundle_ready and not r.executed
