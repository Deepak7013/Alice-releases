from alice.learning.governed import GovernedLearning

def test_governed_learning_accepts_and_records(tmp_path):
    g=GovernedLearning(tmp_path); r=g.evaluate('Remember: ALICE should prefer local knowledge when verified.')
    assert r.accepted and r.persisted and r.topic=='instruction'

def test_governed_learning_rejects_secret(tmp_path):
    r=GovernedLearning(tmp_path).evaluate('Remember: password=abc123')
    assert not r.accepted and r.reason=='secret_like'
