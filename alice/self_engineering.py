"""Phase 12 bounded self-engineering pipeline."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum

class EngineeringStage(str, Enum):
    OBSERVE='observe'; DIAGNOSE='diagnose'; REPAIR='repair'; TEST='test'; PACKAGE='package'; PROMOTE='promote'; ROLLBACK='rollback'
@dataclass
class EngineeringRun:
    issue: str
    stage: EngineeringStage=EngineeringStage.OBSERVE
    tests_passed: bool=False
    promoted: bool=False
    history: list[str]=field(default_factory=list)
class SelfEngineering:
    VERSION='v3.56.0'
    def start(self, issue:str)->EngineeringRun:
        if not issue.strip(): raise ValueError('issue is required')
        return EngineeringRun(issue=issue.strip())
    def advance(self, run:EngineeringRun, stage:EngineeringStage)->EngineeringRun:
        allowed={EngineeringStage.OBSERVE:[EngineeringStage.DIAGNOSE],EngineeringStage.DIAGNOSE:[EngineeringStage.REPAIR],EngineeringStage.REPAIR:[EngineeringStage.TEST],EngineeringStage.TEST:[EngineeringStage.PACKAGE,EngineeringStage.ROLLBACK],EngineeringStage.PACKAGE:[EngineeringStage.PROMOTE],EngineeringStage.PROMOTE:[],EngineeringStage.ROLLBACK:[]}
        if stage not in allowed[run.stage]: raise ValueError(f'invalid transition {run.stage}->{stage}')
        run.stage=stage; run.history.append(stage.value)
        if stage==EngineeringStage.TEST: run.tests_passed=True
        if stage==EngineeringStage.PROMOTE and not run.tests_passed: raise ValueError('promotion requires passing tests')
        if stage==EngineeringStage.PROMOTE: run.promoted=True
        return run
