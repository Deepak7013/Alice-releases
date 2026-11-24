from alice.memory_context.epistemic import EpistemicLedger, EpistemicStatus

def test_asserted_claim_is_not_verified(tmp_path):
    e=EpistemicLedger(tmp_path); r=e.add("local model is installed", source="chat", confidence=.6)
    assert r["status"] == "asserted"
    assert e.get(r["record_id"])["status"] == "asserted"

def test_verification_promotes_claim(tmp_path):
    e=EpistemicLedger(tmp_path); r=e.add("python is available", source="diagnostic")
    out=e.verify(r["record_id"], "python --version returned successfully")
    assert out["status"] == "verified" and out["confidence"] >= .8

def test_superseding_claim_does_not_delete_history(tmp_path):
    e=EpistemicLedger(tmp_path); old=e.add("voice is unknown", source="chat")
    new=e.add("female voice is configured", source="diagnostic", status=EpistemicStatus.VERIFIED, supersedes=old["record_id"])
    assert e.get(old["record_id"])["status"] == "superseded"
    assert e.get(new["record_id"])["status"] == "verified"

def test_disputed_claim_loses_confidence(tmp_path):
    e=EpistemicLedger(tmp_path); r=e.add("browser is connected", confidence=.9)
    out=e.dispute(r["record_id"], "connection test failed")
    assert out["status"] == "disputed" and out["confidence"] <= .4
