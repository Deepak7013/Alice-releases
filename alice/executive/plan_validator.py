"""Preflight validator for executive plans.

Validation is deliberately side-effect free. It checks intent, capability
readiness and explicit verification requirements before a plan reaches the
existing action/approval stack.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Iterable

from alice.self_model.capability_graph import CapabilityGraph

@dataclass(frozen=True)
class PlanStepCheck:
    index: int
    description: str
    capability: str | None
    ready: bool
    reason: str
    missing: tuple[str, ...] = ()
    degraded: tuple[str, ...] = ()

@dataclass(frozen=True)
class PlanValidation:
    valid: bool
    reason: str
    steps: tuple[PlanStepCheck, ...]
    requires_verification: bool

class ExecutivePlanValidator:
    """Validate a proposed plan without executing it or changing permissions."""
    def __init__(self, capabilities):
        self.graph = CapabilityGraph(capabilities)

    def validate(self, steps: Iterable[dict]) -> PlanValidation:
        checks=[]
        requires_verification=False
        for i, raw in enumerate(steps, 1):
            step=dict(raw or {})
            desc=str(step.get("description", "")).strip()
            if not desc:
                return PlanValidation(False, "step_description_required", tuple(checks), requires_verification)
            cap=step.get("capability")
            if cap:
                r=self.graph.readiness(cap)
                checks.append(PlanStepCheck(i, desc, str(cap), r.ready, r.reason, r.missing, r.degraded))
                if not r.ready:
                    return PlanValidation(False, f"capability_not_ready:{cap}", tuple(checks), requires_verification)
            else:
                checks.append(PlanStepCheck(i, desc, None, True, "no_capability_declared"))
            if bool(step.get("side_effect", True)):
                requires_verification=True
        if not checks:
            return PlanValidation(False, "plan_empty", tuple(), False)
        return PlanValidation(True, "preflight_passed", tuple(checks), requires_verification)

    @staticmethod
    def completion_claim_allowed(validation: PlanValidation, evidence: dict | None) -> bool:
        if not validation.valid or not evidence:
            return False
        return bool(evidence.get("ok"))

    @staticmethod
    def to_dict(validation: PlanValidation):
        data=asdict(validation)
        data["steps"]=[asdict(x) for x in validation.steps]
        return data
