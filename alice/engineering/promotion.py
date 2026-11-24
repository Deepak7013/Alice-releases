"""Explicit promotion decision gate; never performs promotion itself."""
from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class PromotionDecision:
    eligible: bool
    reasons: list[str]
    candidate_only: bool=True
    def as_dict(self): return asdict(self)

class PromotionGate:
    def evaluate(self, validation, approval=False, protected_ok=True):
        reasons=[]
        if not validation.get("verified"): reasons.append("candidate_not_verified")
        if not approval: reasons.append("explicit_approval_required")
        if not protected_ok: reasons.append("protected_boundary_failed")
        return PromotionDecision(not reasons,reasons)
