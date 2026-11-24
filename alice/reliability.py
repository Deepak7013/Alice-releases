from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable

@dataclass
class RecoveryEvent:
    step: int; action: str; reason: str=''; success: bool=True

@dataclass
class ReliabilityReport:
    ok: bool; attempts: int; recovered: bool=False; events: list[RecoveryEvent]=field(default_factory=list); error: str=''

class RecoveryEngine:
    """Bounded observe/retry/recover policy. Never changes permissions or safety policy."""
    def __init__(self, max_attempts:int=3): self.max_attempts=max(1,max_attempts)
    def run(self, step:int, action:Callable[[],Any], observe:Callable[[],Any]|None=None,
            verify:Callable[[Any,Any],bool]|None=None, recover:Callable[[Exception,Any],bool]|None=None) -> ReliabilityReport:
        events=[]; last=None
        for attempt in range(1,self.max_attempts+1):
            before=observe() if observe else None
            try:
                outcome=action(); ok=verify(outcome,before) if verify else True
                if ok: return ReliabilityReport(True,attempt,attempt>1,events)
                raise RuntimeError('verification failed')
            except Exception as exc:
                last=exc; events.append(RecoveryEvent(step,'retry',str(exc),False))
                if attempt < self.max_attempts and recover:
                    try:
                        if recover(exc,before): events.append(RecoveryEvent(step,'recover','recovery action applied',True))
                    except Exception as rex: events.append(RecoveryEvent(step,'recover',str(rex),False))
        return ReliabilityReport(False,self.max_attempts,bool(events),events,error=str(last or 'unknown failure'))
