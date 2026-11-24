from dataclasses import dataclass, field
from typing import Any, Callable
from alice.actions.engine import ActionEngine
@dataclass
class Verification:
    ok: bool
    evidence: Any=None
    reason: str=''
@dataclass
class LoopResult:
    status: str
    attempts: int
    evidence: list[Any]=field(default_factory=list)
class VerifiedExecutor:
    """Execute only through ActionEngine, then independently verify and optionally retry boundedly."""
    def __init__(self, actions=None, max_attempts=2, capability_manager=None):
        if max_attempts<1 or max_attempts>5: raise ValueError('max_attempts must be 1..5')
        self.actions=actions or ActionEngine(); self.max_attempts=max_attempts
        self.capability_manager=capability_manager
    def run(self, action:str, executor:Callable[[],Any], verifier:Callable[[Any],Verification|bool], approval=False, capability=None):
        if capability is not None and self.capability_manager is not None:
            if self.capability_manager.get(capability) is None:
                raise ValueError(f'Unknown capability: {capability}')
        rec=self.actions.plan(action)
        if not approval: return LoopResult('awaiting_approval',0,[])
        self.actions.approve(rec.action_id); evidence=[]
        for attempt in range(1,self.max_attempts+1):
            rec=self.actions.execute(rec.action_id,executor)
            if rec.status.value!='executed':
                self._record_failure(capability,rec.error or 'action execution failed')
                return LoopResult('failed',attempt,evidence)
            try:
                v=verifier(rec.result)
            except Exception as exc:
                self.actions.verify(rec.action_id,lambda _:False,'verification_error')
                self._record_failure(capability,f'verification error: {exc}')
                raise
            v=v if isinstance(v,Verification) else Verification(bool(v),rec.result,'' if v else 'verification failed')
            evidence.append(v.evidence)
            if v.ok:
                self.actions.verify(rec.action_id,lambda _:True,v.reason or 'verified')
                self._record_success(capability,v.reason or 'action independently verified')
                return LoopResult('verified',attempt,evidence)
            if attempt<self.max_attempts:
                # Explicit retry is represented as a new approved action, preserving audit history.
                rec=self.actions.plan(action+f' [retry {attempt+1}]'); self.actions.approve(rec.action_id)
        self._record_failure(capability,'action verification failed after bounded attempts')
        return LoopResult('failed_verification',self.max_attempts,evidence)

    def _record_success(self, capability, note):
        if capability is not None and self.capability_manager is not None:
            self.capability_manager.record_success(capability, note=note)

    def _record_failure(self, capability, error):
        if capability is not None and self.capability_manager is not None:
            self.capability_manager.record_failure(capability, error, degraded=True)
