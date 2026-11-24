"""Phase 8 bounded planning council for ALICE.

The council separates proposal generation from synthesis and verification. It
never executes tools, grants permissions, or converts a hypothetical request
into an action.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import time
from typing import Any, Callable


@dataclass
class PlanProposal:
    role: str
    plan: Any = None
    confidence: float = 0.0
    rationale: str = ""
    risks: list[str] | None = None
    ok: bool = True
    error: str = ""

    def to_dict(self):
        d = asdict(self)
        d["risks"] = list(self.risks or [])[:16]
        d["confidence"] = max(0.0, min(1.0, float(self.confidence)))
        return d


class PlanningCouncil:
    """Bounded Planner/Analyst/Critic -> Synthesizer -> Verifier pipeline."""

    VERSION = "v3.40.0"
    DEFAULT_ROLES = ("planner", "analyst", "critic")

    def __init__(self, roles=None, synthesizer=None, verifier=None, max_proposals=3):
        self.roles: dict[str, Callable] = dict(roles or {})
        self.synthesizer = synthesizer
        self.verifier = verifier
        self.max_proposals = max(1, min(int(max_proposals), 8))

    def register(self, role: str, handler: Callable):
        role = str(role).strip().lower()
        if not role:
            raise ValueError("role is required")
        if not callable(handler):
            raise TypeError("role handler must be callable")
        self.roles[role[:64]] = handler
        return sorted(self.roles)

    def _proposal(self, role, task, context):
        try:
            raw = self.roles[role](task, context) if context is not None else self.roles[role](task)
            if isinstance(raw, PlanProposal):
                raw.role = role
                return raw
            if isinstance(raw, dict):
                return PlanProposal(role, raw.get("plan", raw), float(raw.get("confidence", .5)),
                                    str(raw.get("rationale", "")), list(raw.get("risks", [])))
            return PlanProposal(role, raw, .5)
        except Exception as exc:
            return PlanProposal(role, ok=False, error=str(exc)[:500])

    def deliberate(self, task, *, context=None, roles=None):
        selected = [r for r in (roles or self.DEFAULT_ROLES) if r in self.roles][:self.max_proposals]
        if not selected:
            raise ValueError("no planning roles available")
        proposals = [self._proposal(r, task, context) for r in selected]
        good = [p for p in proposals if p.ok and p.plan is not None]
        if not good:
            return self._result(task, proposals, None, False, "No valid plan proposals")

        if self.synthesizer:
            try:
                synthesis = self.synthesizer(task, [p.to_dict() for p in good], context)
            except Exception as exc:
                synthesis = None
                synth_error = str(exc)[:500]
            else:
                synth_error = ""
        else:
            # Conservative deterministic synthesis: prefer highest confidence,
            # then lowest declared risk count, then stable role ordering.
            winner = sorted(good, key=lambda p: (-p.confidence, len(p.risks or []), p.role))[0]
            synthesis = winner.plan
            synth_error = ""

        if synthesis is None:
            return self._result(task, proposals, None, False, synth_error or "Synthesis failed")

        verified = False
        verification = {"verified": False, "reason": "No verifier configured"}
        if self.verifier:
            try:
                verdict = self.verifier(task, synthesis, context)
                if isinstance(verdict, dict):
                    verified = bool(verdict.get("verified", verdict.get("ok", False)))
                    verification = dict(verdict)
                else:
                    verified = bool(verdict)
                    verification = {"verified": verified}
            except Exception as exc:
                verification = {"verified": False, "reason": str(exc)[:500]}
        return self._result(task, proposals, synthesis, verified, verification=verification)

    def _result(self, task, proposals, plan, verified, reason="", verification=None):
        payload = [(p.role, p.plan, p.confidence, p.ok) for p in proposals]
        digest = hashlib.sha256(repr(payload).encode()).hexdigest()[:16]
        agreement = sum(1 for p in proposals if p.ok) / max(1, len(proposals))
        return {
            "version": self.VERSION,
            "task": str(task)[:2000],
            "proposals": [p.to_dict() for p in proposals],
            "selected_plan": plan,
            "agreement": agreement,
            "verified": bool(verified),
            "verification": verification or {"verified": False, "reason": reason},
            "reason": reason,
            "requires_execution_verification": bool(plan is not None),
            "no_execution_performed": True,
            "digest": digest,
            "created_at": time.time(),
        }
