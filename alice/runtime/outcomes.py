"""Validation helpers for trusted runtime outcome envelopes."""
from __future__ import annotations


def has_verified_action_evidence(evidence) -> bool:
    """Require at least one successful independent observer and no open steps."""
    if not isinstance(evidence,dict) or evidence.get("observed") is not True:
        return False
    actions=evidence.get("verified_actions")
    if not isinstance(actions,list) or not actions or evidence.get("unverified_steps"):
        return False
    return all(
        isinstance(row,dict)
        and bool(str(row.get("tool", "")).strip())
        and row.get("postcondition_ok") is True
        and isinstance(row.get("postcondition_evidence"),dict)
        and row["postcondition_evidence"].get("observed") is True
        for row in actions
    )


def is_verified_action_outcome(outcome) -> bool:
    return (isinstance(outcome,dict) and outcome.get("verified") is True
            and has_verified_action_evidence(outcome.get("verification_evidence")))
