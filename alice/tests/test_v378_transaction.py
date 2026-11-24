from alice.engineering.transaction import plan_promotion
def test_transaction_requires_approval():
 assert not plan_promotion('c','t',['alice/x.py']).executable
 assert plan_promotion('c','t',['alice/x.py'],True).executable
def test_protected_path_blocks(): assert not plan_promotion('c','t',['alice_workspace/x'],True).executable
