from __future__ import annotations
from dataclasses import dataclass, asdict
@dataclass(frozen=True)
class ContinuationDecision:
    unfinished: bool; blocker_clear: bool; safe_to_continue: bool; action: str
    def as_dict(self): return asdict(self)
def decide_continuation(unfinished, blocker_clear, safe_to_continue=True):
    u,b,s=bool(unfinished),bool(blocker_clear),bool(safe_to_continue)
    action='complete' if not u else ('continue' if b and s else 'pause_for_safety' if b else 'await_missing_decision')
    return ContinuationDecision(u,b,s,action)
