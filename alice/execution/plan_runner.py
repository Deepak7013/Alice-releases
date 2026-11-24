from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Any
from alice.actions.engine import ActionEngine
from alice.planning.models import Plan, PlanStep

@dataclass
class StepOutcome:
    step_id: str
    status: str
    action_id: str | None = None
    result: Any = None
    error: str | None = None

@dataclass
class ExecutionResult:
    plan_id: str
    status: str
    steps: list[StepOutcome] = field(default_factory=list)

class PlanExecutor:
    """Connects GoalPlanner output to the ActionEngine without bypassing approval."""
    def __init__(self, actions=None): self.actions=actions or ActionEngine()
    def execute(self, plan: Plan, runner: Callable[[PlanStep],Any]) -> ExecutionResult:
        plan.validate(); completed=set(); out=[]
        for step in plan.steps:
            if any(dep not in completed for dep in step.depends_on):
                out.append(StepOutcome(step.step_id,'blocked',error='dependency not completed'))
                return ExecutionResult(plan.plan_id,'blocked',out)
            rec=self.actions.plan(step.action)
            if step.requires_approval:
                out.append(StepOutcome(step.step_id,'awaiting_approval',rec.action_id))
                return ExecutionResult(plan.plan_id,'awaiting_approval',out)
            self.actions.approve(rec.action_id)
            rec=self.actions.execute(rec.action_id,lambda s=step: runner(s))
            if rec.status.value!='executed':
                out.append(StepOutcome(step.step_id,'failed',rec.action_id,error=rec.error))
                return ExecutionResult(plan.plan_id,'failed',out)
            out.append(StepOutcome(step.step_id,'executed',rec.action_id,rec.result)); completed.add(step.step_id)
        return ExecutionResult(plan.plan_id,'executed',out)
    def approve_and_continue(self, plan: Plan, result: ExecutionResult, runner: Callable[[PlanStep],Any]) -> ExecutionResult:
        if result.status!='awaiting_approval': raise ValueError('result is not awaiting approval')
        completed={x.step_id for x in result.steps if x.status=='executed'}
        start=len(result.steps); steps=plan.steps[start:]
        if not result.steps or result.steps[-1].status!='awaiting_approval': raise ValueError('no pending approval')
        pending_id=result.steps[-1].action_id; self.actions.approve(pending_id)
        rec=self.actions.execute(pending_id,lambda s=plan.steps[start]: runner(s))
        result.steps[-1]=StepOutcome(plan.steps[start].step_id,'executed' if rec.status.value=='executed' else 'failed',pending_id,rec.result,rec.error)
        if rec.status.value!='executed': result.status='failed'; return result
        completed.add(plan.steps[start].step_id)
        for step in plan.steps[start+1:]:
            if any(d not in completed for d in step.depends_on): result.status='blocked'; result.steps.append(StepOutcome(step.step_id,'blocked',error='dependency not completed')); return result
            ar=self.actions.plan(step.action)
            if step.requires_approval: result.status='awaiting_approval'; result.steps.append(StepOutcome(step.step_id,'awaiting_approval',ar.action_id)); return result
            self.actions.approve(ar.action_id); ar=self.actions.execute(ar.action_id,lambda s=step: runner(s))
            result.steps.append(StepOutcome(step.step_id,'executed' if ar.status.value=='executed' else 'failed',ar.action_id,ar.result,ar.error))
            if ar.status.value!='executed': result.status='failed'; return result
            completed.add(step.step_id)
        result.status='executed'; return result
