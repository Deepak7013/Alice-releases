"""Phase 9 Executive Action Engine.

Bridges a verified plan to the existing ActionEngine while preserving the
existing permission authority and requiring post-execution verification.
Planning is deliberately separate from execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .engine import ActionEngine
from .models import ActionRecord, ActionStatus


@dataclass
class ExecutiveResult:
    action_ids: list[str] = field(default_factory=list)
    records: list[ActionRecord] = field(default_factory=list)
    executed: int = 0
    verified: int = 0
    failed: int = 0
    blocked: int = 0
    message: str = ""


class ExecutiveActionEngine:
    """Execute only an explicitly approved, verification-ready action plan.

    This class does not grant permissions. Approval must already be recorded by
    ActionEngine, and every executed action must pass a supplied verifier before
    it is counted as completed.
    """

    VERSION = "v3.41.0"

    def __init__(self, action_engine: Optional[ActionEngine] = None):
        self.actions = action_engine or ActionEngine()

    def prepare(self, plan: dict[str, Any], *, planning_verified: bool = False) -> list[str]:
        if not planning_verified:
            raise PermissionError("verified planning result required before execution")
        steps = plan.get("steps") if isinstance(plan, dict) else None
        if not isinstance(steps, list) or not steps:
            raise ValueError("plan must contain non-empty steps")
        ids = []
        for step in steps:
            if not isinstance(step, dict) or not str(step.get("action", "")).strip():
                raise ValueError("each plan step requires an action")
            ids.append(self.actions.plan(str(step["action"])).action_id)
        return ids

    def approve_all(self, action_ids: list[str]) -> list[ActionRecord]:
        return [self.actions.approve(action_id) for action_id in action_ids]

    def execute_and_verify(
        self,
        action_ids: list[str],
        executors: list[Callable[[], object]],
        verifiers: list[Callable[[object], bool]],
    ) -> ExecutiveResult:
        if not (len(action_ids) == len(executors) == len(verifiers)):
            raise ValueError("action, executor and verifier counts must match")
        result = ExecutiveResult(action_ids=list(action_ids))
        for action_id, executor, verifier in zip(action_ids, executors, verifiers):
            record = self.actions.execute(action_id, executor)
            result.records.append(record)
            if record.status == ActionStatus.EXECUTED:
                result.executed += 1
                record = self.actions.verify(action_id, verifier)
                result.records.append(record)
                if record.status == ActionStatus.VERIFIED:
                    result.verified += 1
                else:
                    result.failed += 1
            else:
                result.failed += 1
        result.message = (
            "All actions executed and verified."
            if result.verified == len(action_ids)
            else "Execution was incomplete or verification failed; do not claim completion."
        )
        return result
