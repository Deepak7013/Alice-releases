from alice.deployment.upgrade_bundle import plan_upgrade
def test_upgrade_bundle_requires_verification_and_approval():
 assert not plan_upgrade('3.84.0','c',['a.py'],True,False).ready
 assert plan_upgrade('3.84.0','c',['a.py'],True,True).ready
