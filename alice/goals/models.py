from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
import time

class GoalStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class GoalStep:
    id: str
    title: str
    request: str = ""
    status: str = "pending"
    depends_on: list[str] = field(default_factory=list)
    attempts: int = 0
    last_error: str = ""
    result: str = ""
    updated_at: float = field(default_factory=time.time)

@dataclass
class Goal:
    id: str
    title: str
    objective: str
    status: str = GoalStatus.ACTIVE.value
    priority: float = 0.5
    deadline: float | None = None
    steps: list[GoalStep] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self):
        return asdict(self)
