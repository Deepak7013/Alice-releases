"""ALICE v4.5 bounded action verification envelope.

A reasoning result is not treated as successful execution. An action must carry
expected-state information and receive explicit observation evidence before it is
classified as verified.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class VerificationDecision:
    verified: bool
    recoverable: bool
    reason: str

class VerificationEnvelope:
    def evaluate(self, *, action_id, expected_state, observed_state, execution_ok, evidence=None):
        if not str(action_id).strip():
            return VerificationDecision(False, False, "missing_action_id")
        if not isinstance(expected_state, dict) or not expected_state:
            return VerificationDecision(False, False, "missing_expected_state")
        if not isinstance(observed_state, dict):
            return VerificationDecision(False, bool(execution_ok), "missing_observation")
        if not execution_ok:
            return VerificationDecision(False, True, "execution_failed")
        if not evidence or not str(evidence).strip():
            return VerificationDecision(False, True, "missing_verification_evidence")
        for key, expected in expected_state.items():
            if observed_state.get(key) != expected:
                return VerificationDecision(False, True, "state_mismatch")
        return VerificationDecision(True, False, "verified")
