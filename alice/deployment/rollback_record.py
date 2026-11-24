from __future__ import annotations
from dataclasses import dataclass, asdict
@dataclass(frozen=True)
class RollbackDecision:
    healthy: bool; rollback_available: bool; explicit_approval: bool; action: str
    def as_dict(self): return asdict(self)
def decide_rollback(healthy, rollback_available, explicit_approval=False):
    h,a,p=bool(healthy),bool(rollback_available),bool(explicit_approval)
    action='retain_current' if h else ('rollback' if a and p else 'await_explicit_rollback_approval' if a else 'quarantine_and_recover')
    return RollbackDecision(h,a,p,action)
