from __future__ import annotations
from dataclasses import dataclass,asdict

@dataclass(frozen=True)
class AcquisitionPlan:
    capability:str; local_gap:bool; external_research_allowed:bool; steps:tuple[str,...]; executable:bool=False
    def as_dict(self): return asdict(self)

def plan_capability_acquisition(capability,local_gap=True,external_research_allowed=False):
    cap=str(capability).strip()
    if not cap: raise ValueError('capability is required')
    steps=('identify_gap','inspect_existing_local_capabilities','define_testable_acceptance_criteria','research_or_design_candidate' if external_research_allowed else 'design_local_candidate','sandbox_candidate','run_regression_tests','request_promotion_approval')
    return AcquisitionPlan(cap,bool(local_gap),bool(external_research_allowed),steps,False)
