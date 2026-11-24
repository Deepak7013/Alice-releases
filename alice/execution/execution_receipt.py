"""Immutable evidence receipt for governed tool execution.

The receipt records what the execution boundary observed. It does not itself
assert authority, perform verification, or execute a tool.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionReceipt:
    action_id: str
    tool: str
    admitted: bool
    execution_ok: bool
    verified: bool
    outcome: str
    evidence: str = ""


class ExecutionReceiptFactory:
    """Create conservative execution evidence without inferring success."""

    _MAX_ACTION_ID = 512
    _MAX_TOOL = 512
    _MAX_OUTCOME = 128
    _MAX_EVIDENCE = 4096

    def create(
        self,
        *,
        action_id: str,
        tool: str,
        admitted: bool,
        execution_ok: bool,
        verified: bool,
        outcome: str,
        evidence: str = "",
    ) -> ExecutionReceipt:
        # Do not coerce untrusted values: bool("false") is True, and str(None)
        # creates plausible-looking identifiers that were never supplied.
        if not isinstance(action_id, str) or not action_id.strip():
            raise ValueError("action_id_required")
        if len(action_id.strip()) > self._MAX_ACTION_ID:
            raise ValueError("action_id_too_long")
        if not isinstance(tool, str) or not tool.strip():
            raise ValueError("tool_required")
        if len(tool.strip()) > self._MAX_TOOL:
            raise ValueError("tool_too_long")
        if not isinstance(outcome, str) or not outcome.strip():
            raise ValueError("outcome_required")
        if len(outcome.strip()) > self._MAX_OUTCOME:
            raise ValueError("outcome_too_long")
        if any(type(value) is not bool for value in (admitted, execution_ok, verified)):
            raise ValueError("receipt_flags_must_be_boolean")
        if not isinstance(evidence, str):
            raise ValueError("evidence_must_be_string")
        if len(evidence) > self._MAX_EVIDENCE:
            raise ValueError("evidence_too_long")
        if verified and not execution_ok:
            raise ValueError("verified_requires_execution_success")
        if execution_ok and not admitted:
            raise ValueError("execution_success_requires_admission")
        return ExecutionReceipt(
            action_id=action_id.strip(),
            tool=tool.strip(),
            admitted=admitted,
            execution_ok=execution_ok,
            verified=verified,
            outcome=outcome.strip(),
            evidence=evidence,
        )
