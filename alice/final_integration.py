"""Phase 15 unified executive integration facade."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable
from .verification import ObserveVerifyRecover, Observation
from .learning import LearningStore
@dataclass
class IntegratedOutcome:
    executed: bool; verified: bool; learned: bool; message: str
class AliceIntegratedExecutive:
    VERSION='v3.47.0'
    def __init__(self, learning: LearningStore|None=None):
        self.learning=learning; self.recovery=ObserveVerifyRecover()
    def complete(self, action:Callable[[],Any], observe:Callable[[],Observation], recover:Callable[[],Any]|None=None, lesson:tuple[str,str]|None=None):
        try: action()
        except Exception as exc: return IntegratedOutcome(False,False,False,f'action failed: {exc}')
        result=self.recovery.run(observe,recover)
        learned=False
        if result.verified and lesson and self.learning:
            self.learning.learn(*lesson); learned=True
        return IntegratedOutcome(True,result.verified,learned,result.message)
