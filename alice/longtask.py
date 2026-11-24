from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class TaskStatus(str, Enum):
    PENDING='pending'; RUNNING='running'; WAITING='waiting'; PAUSED='paused'; FAILED='failed'; COMPLETED='completed'; BLOCKED='blocked'

@dataclass
class TaskCheckpoint:
    task_id: str; step_index: int; state: dict[str, Any] = field(default_factory=dict)

@dataclass
class LongTask:
    task_id: str; goal: str; steps: list[dict[str, Any]] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING; cursor: int = 0
    completed: list[int] = field(default_factory=list); attempts: dict[int,int] = field(default_factory=dict)
    checkpoints: list[TaskCheckpoint] = field(default_factory=list); result: Any = None; error: str = ''

class LongTaskManager:
    """Persistent-friendly task state machine. Execution remains delegated to existing safety/runtime layers."""
    def __init__(self, max_attempts: int = 3): self.max_attempts=max(1,max_attempts); self.tasks={}
    def create(self, task_id: str, goal: str, steps: list[dict[str,Any]]) -> LongTask:
        if not task_id or not goal.strip(): raise ValueError('task_id and goal are required')
        task=LongTask(task_id,goal,list(steps)); self.tasks[task_id]=task; return task
    def checkpoint(self, task_id: str, state: dict[str,Any]|None=None) -> TaskCheckpoint:
        t=self._get(task_id); cp=TaskCheckpoint(t.task_id,t.cursor,dict(state or {})); t.checkpoints.append(cp); return cp
    def resume(self, task_id: str) -> LongTask:
        t=self._get(task_id); t.status=TaskStatus.RUNNING; return t
    def pause(self, task_id: str) -> LongTask:
        t=self._get(task_id); t.status=TaskStatus.PAUSED; return t
    def next_step(self, task_id: str):
        t=self._get(task_id)
        if t.cursor >= len(t.steps): t.status=TaskStatus.COMPLETED; return None
        t.status=TaskStatus.RUNNING; return t.steps[t.cursor]
    def record_success(self, task_id: str, result: Any=None) -> LongTask:
        t=self._get(task_id); t.completed.append(t.cursor); t.cursor += 1; t.result=result
        t.status=TaskStatus.COMPLETED if t.cursor >= len(t.steps) else TaskStatus.RUNNING; return t
    def record_failure(self, task_id: str, error: str, retryable: bool=True) -> LongTask:
        t=self._get(task_id); t.error=error; t.attempts[t.cursor]=t.attempts.get(t.cursor,0)+1
        if retryable and t.attempts[t.cursor] < self.max_attempts: t.status=TaskStatus.RUNNING
        else: t.status=TaskStatus.FAILED
        return t
    def _get(self, task_id):
        if task_id not in self.tasks: raise KeyError(task_id)
        return self.tasks[task_id]
