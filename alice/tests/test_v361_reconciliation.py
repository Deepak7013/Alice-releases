from alice.memory_context.epistemic import EpistemicLedger, EpistemicStatus
from alice.memory_context.reconciliation import EpistemicReconciler

def test_reconciler_detects_duplicate(tmp_path):
    ledger = EpistemicLedger(tmp_path)
    old = ledger.add("ALICE has a local engineering model", source="chat", confidence=.7)
    rows = EpistemicReconciler(ledger).compare("ALICE has a local engineering model")
    assert rows and rows[0].status == "duplicate" and old["record_id"] in rows[0].related_ids

def test_reconciler_detects_polarity_conflict(tmp_path):
    ledger = EpistemicLedger(tmp_path)
    ledger.add("browser automation is enabled", source="chat")
    rows = EpistemicReconciler(ledger).compare("browser automation is not enabled")
    assert any(x.status == "potential_conflict" for x in rows)

def test_trust_rewards_verification_but_not_authority(tmp_path):
    ledger = EpistemicLedger(tmp_path)
    r = ledger.add("python is available", source="diagnostic", confidence=.7)
    assert EpistemicReconciler(ledger).current_trust(r["record_id"]) == .7
    ledger.verify(r["record_id"], "python --version succeeded")
    assert EpistemicReconciler(ledger).current_trust(r["record_id"]) > .7
