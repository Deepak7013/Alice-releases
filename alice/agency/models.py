"""Persistent models for Alice's controlled agency layer."""
from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List
import time, uuid

class GoalStatus:
    ACTIVE="ACTIVE"; PAUSED="PAUSED"; COMPLETED="COMPLETED"; BLOCKED="BLOCKED"; CANCELLED="CANCELLED"

class Initiative:
    OBSERVE="observe"; RESEARCH="research"; PLAN="plan"; RECOMMEND="recommend"; EXECUTE="execute"; WAIT="wait"

@dataclass
class Goal:
    id: str
    title: str
    description: str
    priority: int = 50
    status: str = GoalStatus.ACTIVE
    constraints: List[str] = field(default_factory=list)
    progress: float = 0.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @classmethod
    def create(cls, title, description="", priority=50, constraints=None):
        return cls(uuid.uuid4().hex[:12], title, description, int(priority), constraints=list(constraints or []))

    def to_dict(self): return asdict(self)

@dataclass
class Observation:
    event: str
    payload: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    source: str = "system"

@dataclass
class InitiativeDecision:
    action: str
    reason: str
    goal_id: str | None = None
    requires_approval: bool = False
    confidence: float = 0.0
    evidence: List[str] = field(default_factory=list)

    def to_dict(self): return asdict(self)
