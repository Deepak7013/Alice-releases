
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class Experience:
    task_type: str
    workflow: str
    success: bool
    duration_ms: int = 0
    error_class: str | None = None
    outcome: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

@dataclass
class Workflow:
    task_type: str
    workflow: str
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    confidence: float = 0.0
    promoted: bool = False
    regression_count: int = 0

    def record(self, success: bool):
        self.attempts += 1
        if success:
            self.successes += 1
            self.regression_count = 0
        else:
            self.failures += 1
            self.regression_count += 1
        # Laplace-smoothed success estimate.
        self.confidence = (self.successes + 1) / (self.attempts + 2)

@dataclass
class LearningDecision:
    action: str
    workflow: Workflow
    reason: str
