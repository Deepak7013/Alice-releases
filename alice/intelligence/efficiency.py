"""Time-saving strategy policy for Alice.

Alice prefers the cheapest reliable path first, escalates only when uncertainty
or task complexity justifies it, and records the reason for each choice.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class EfficiencyDecision:
    path: str
    reason: str
    confidence: float
    estimated_cost: str

class EfficiencyPolicy:
    def choose(self, *, direct_confidence=0.0, transfer_confidence=0.0,
               deterministic_available=True, visual_required=False,
               provider_available=False, complexity="normal"):
        dc=float(direct_confidence); tc=float(transfer_confidence)
        if dc>=0.72:
            return EfficiencyDecision("reuse_cached_experience","high-confidence prior success",dc,"low")
        if tc>=0.68:
            return EfficiencyDecision("reuse_transferred_experience","strong supported cross-domain method",tc,"low")
        if deterministic_available and complexity in {"low","normal"} and not visual_required:
            return EfficiencyDecision("use_local_algorithm","deterministic local method is sufficient",0.55,"low")
        if visual_required and provider_available:
            return EfficiencyDecision("use_multimodal_review","visual ambiguity justifies expert review",0.60,"medium")
        if deterministic_available:
            return EfficiencyDecision("use_local_algorithm_with_verification","safe local path with verification",0.50,"low")
        if provider_available:
            return EfficiencyDecision("escalate_to_ai_provider","no sufficient local method",0.45,"medium")
        return EfficiencyDecision("request_missing_capability","no reliable execution path is available",0.0,"blocked")

    @staticmethod
    def optimistic_status(ok, confidence=0.0, blocked_reason=None):
        """Optimistic means action-oriented, never falsely certain."""
        if ok and confidence>=0.75: return "strongly_positive"
        if ok: return "positive_with_verification"
        if blocked_reason: return "blocked_with_next_step"
        return "uncertain_with_safe_next_step"
