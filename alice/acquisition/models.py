
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class AcquisitionStage(str, Enum):
    PROPOSED="proposed"
    RESEARCH="research"
    DESIGNED="designed"
    VALIDATING="validating"
    SANDBOX_TEST="sandbox_test"
    SECURITY_REVIEW="security_review"
    READY="ready"
    ACTIVATED="activated"
    REJECTED="rejected"

@dataclass
class CapabilityProposal:
    name: str
    task_type: str
    workflow: str
    source: str = "learned_workflow"
    confidence: float = 0.0
    requested_scopes: list[str] = field(default_factory=list)
    evidence: list[dict[str,Any]] = field(default_factory=list)
    stage: AcquisitionStage = AcquisitionStage.PROPOSED
    rejection_reason: str = ""

    def transition(self, stage: AcquisitionStage):
        self.stage=stage
