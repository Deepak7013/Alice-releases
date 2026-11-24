"""Deterministic gate for bounded execution recovery decisions."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class RecoveryDecision:
    recover: bool
    reason: str
    next_attempt: int = 0

class RecoveryGate:
    def decide(self, *, verification_ok: bool, recoverable: bool,
               attempts_used: int, max_attempts: int, authority_available: bool = True) -> RecoveryDecision:
        if verification_ok:
            return RecoveryDecision(False, "verified_success", attempts_used)
        if not recoverable:
            return RecoveryDecision(False, "not_recoverable", attempts_used)
        if not authority_available:
            return RecoveryDecision(False, "authority_unavailable", attempts_used)
        if attempts_used < 0 or max_attempts < 0:
            return RecoveryDecision(False, "invalid_budget", attempts_used)
        if attempts_used >= max_attempts:
            return RecoveryDecision(False, "recovery_budget_exhausted", attempts_used)
        return RecoveryDecision(True, "bounded_recovery_allowed", attempts_used + 1)
