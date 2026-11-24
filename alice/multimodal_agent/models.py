from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any
import time

class LoopStage(str, Enum):
    PLAN = "plan"
    RESEARCH = "research"
    UNDERSTAND = "understand"
    CREATE = "create"
    ACT = "act"
    VERIFY = "verify"
    RECOVER = "recover"
    COMPLETE = "complete"
    FAILED = "failed"

@dataclass
class AgentStep:
    stage: LoopStage
    action: str
    status: str = "pending"
    output: Any = None
    error: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

@dataclass
class MultimodalGoal:
    goal: str
    evidence_paths: list[str] = field(default_factory=list)
    research: bool = True
    create: bool = False
    act: bool = False
    verify: bool = True
    max_recoveries: int = 2
    context: dict[str, Any] = field(default_factory=dict)

@dataclass
class AgentRun:
    id: str
    goal: MultimodalGoal
    status: str = "pending"
    steps: list[AgentStep] = field(default_factory=list)
    result: Any = None
    recoveries: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self):
        return asdict(self)
