from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class AcquisitionAcceptance:
    capability: str
    tests_required: int
    tests_passed: int
    sandbox_verified: bool
    promotion_allowed: bool
    reason: str

def evaluate(capability, *, tests_required, tests_passed, sandbox_verified, external=False):
    cap=str(capability).strip()
    required=int(tests_required); passed=int(tests_passed)
    if not cap: raise ValueError('capability is required')
    if required < 1 or passed < 0: raise ValueError('invalid test counts')
    if passed > required: raise ValueError('passed tests cannot exceed required tests')
    if passed != required: return AcquisitionAcceptance(cap,required,passed,bool(sandbox_verified),False,'regression tests incomplete')
    if not sandbox_verified: return AcquisitionAcceptance(cap,required,passed,False,False,'sandbox verification required')
    if external: return AcquisitionAcceptance(cap,required,passed,True,False,'external acquisition requires explicit promotion approval')
    return AcquisitionAcceptance(cap,required,passed,True,True,'local candidate meets acceptance criteria')
