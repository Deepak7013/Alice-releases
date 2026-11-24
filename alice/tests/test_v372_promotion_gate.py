from alice.engineering.promotion import PromotionGate

def test_promotion_requires_verification_and_explicit_approval():
    g=PromotionGate()
    r=g.evaluate({"verified":True},approval=False)
    assert r.eligible is False and "explicit_approval_required" in r.reasons
    r=g.evaluate({"verified":True},approval=True)
    assert r.eligible is True and r.candidate_only is True

def test_unverified_candidate_cannot_promote():
    r=PromotionGate().evaluate({"verified":False},approval=True)
    assert r.eligible is False
