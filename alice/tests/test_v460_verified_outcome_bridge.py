from dataclasses import dataclass
from alice.learning.verified_outcome_bridge import VerifiedOutcomeBridge

@dataclass
class V:
    verified: bool
    reason: str
    evidence: str = ""

def test_verified_outcome_becomes_promotable_lesson():
    b=VerifiedOutcomeBridge()
    r=b.learn(action_id="a1", verification=V(True,"verified","observed"), summary="window reached")
    assert r["learned"] and r["promotable"]

def test_unverified_outcome_cannot_be_promoted():
    b=VerifiedOutcomeBridge()
    r=b.learn(action_id="a2", verification=V(False,"state_mismatch","observed"))
    assert not r["learned"] and not r["promotable"]
    try: b.promote(0); assert False
    except ValueError as e: assert str(e)=="only_verified_success_can_be_promoted"

def test_promotion_is_explicit():
    b=VerifiedOutcomeBridge(); b.learn(action_id="a3", verification=V(True,"verified","proof"))
    p=b.promote(0); assert p.promoted is True
