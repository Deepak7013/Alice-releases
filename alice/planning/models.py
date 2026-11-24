
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

class PlanStatus(str, Enum):
    DRAFT="draft"
    READY="ready"
    BLOCKED="blocked"

@dataclass(frozen=True)
class Goal:
    text: str
    constraints: tuple[str, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.text.strip():
            raise ValueError("goal text is required")

@dataclass
class PlanStep:
    step_id: str
    action: str
    depends_on: list[str] = field(default_factory=list)
    consequence: str = "low"
    requires_approval: bool = False
    rationale: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class Plan:
    plan_id: str
    goal: Goal
    steps: list[PlanStep]
    status: PlanStatus = PlanStatus.DRAFT
    assumptions: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)

    def validate(self):
        ids = [s.step_id for s in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate plan step id")
        known = set(ids)
        for s in self.steps:
            if s.step_id in s.depends_on:
                raise ValueError("step cannot depend on itself")
            if any(d not in known for d in s.depends_on):
                raise ValueError(f"unknown dependency in {s.step_id}")
            if s.consequence not in {"low","medium","high","critical"}:
                raise ValueError("invalid consequence level")
        return True
