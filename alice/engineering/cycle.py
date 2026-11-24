"""Controlled proposal-to-candidate engineering cycle. No promotion is performed."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from .engine import EngineeringEngine
from .candidate_sandbox import CandidateSandbox
from .validation import CandidateValidator

@dataclass(frozen=True)
class EngineeringCycleResult:
    proposal_id: str
    plan_name: str
    candidate_path: str
    verified: bool
    tests_passed: int
    tests_failed: int
    promoted: bool = False
    def as_dict(self): return asdict(self)

class GovernedEngineeringCycle:
    def __init__(self, engine=None, validator=None):
        self.engine=engine or EngineeringEngine(); self.validator=validator or CandidateValidator()
    def run(self, proposal_id, goal, source_root, workspace, changes, test_fn=None):
        plan=self.engine.plan(goal)
        sandbox=CandidateSandbox(source_root,workspace); candidate=sandbox.create(); sandbox.apply(changes)
        result=self.validator.validate(candidate,test_fn)
        return EngineeringCycleResult(str(proposal_id),plan.goal.name,str(candidate),result.verified,result.tests_passed,result.tests_failed,False)
