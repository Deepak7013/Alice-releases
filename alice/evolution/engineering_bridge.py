"""Governed bridge from approved improvement proposals to candidate engineering.

The bridge can plan and preflight a candidate change, but never applies source
changes or grants authority. Promotion remains an explicit downstream action.
"""
from __future__ import annotations
from dataclasses import dataclass
from .proposals import ImprovementProposalLedger
from ..engineering.engine import EngineeringEngine
from ..engineering.gate import SelfEngineeringGate
from ..engineering.models import EngineeringGoal, ProjectPlan

@dataclass(frozen=True)
class CandidateChange:
    path: str
    content: str

class ProposalEngineeringBridge:
    def __init__(self, ledger: ImprovementProposalLedger, engine=None, gate=None):
        self.ledger = ledger
        self.engine = engine or EngineeringEngine()
        self.gate = gate or SelfEngineeringGate()

    def prepare(self, proposal_id: str) -> ProjectPlan:
        row = next((x for x in self.ledger.list() if x.get("proposal_id") == proposal_id), None)
        if not row:
            raise KeyError(f"unknown proposal: {proposal_id}")
        if row.get("status") != "engineering_review":
            raise PermissionError("proposal must be approved for engineering review")
        goal = EngineeringGoal(
            name=f"Improve {row.get('area', 'system')}",
            description=row.get("problem", ""),
            constraints=["do not bypass permissions", "preserve protected data", "candidate only"],
            acceptance_criteria=[row.get("expected_benefit", "")],
        )
        return self.engine.plan(goal)

    def preflight_candidate(self, root, proposal_id: str, changes: list[dict]) -> dict:
        self.prepare(proposal_id)
        normalized = [{"path": str(x["path"]), "content": str(x.get("content", ""))} for x in changes]
        impact = self.gate.preflight(root, normalized)
        return {"proposal_id": proposal_id, "candidate_only": True, "impact": impact}
