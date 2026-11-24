"""Join persistent goal steps to runtime postconditions and recovery checkpoints."""
from __future__ import annotations

from pathlib import Path

from .engine import GoalEngine
from ..horizon.task_continuity import TaskContinuityStore
from ..runtime.outcomes import is_verified_action_outcome


class VerifiedGoalWorkflow:
    """Complete goal steps only from ALICE Runtime's observed mutation evidence."""

    def __init__(self, root, runtime, *, goals=None, continuity=None, world=None):
        self.root=Path(root).resolve()
        self.runtime=runtime
        self.goals=goals or GoalEngine(self.root)
        self.continuity=continuity or TaskContinuityStore(self.root)
        self.world=world

    def _record_world_step(self, goal_id, step_id, *, verified=None, approval_required=False):
        if self.world is None: return
        try:
            step=self.goals.get_step(goal_id,step_id)
            state={"goal_id":str(goal_id),"step_id":str(step_id),
                   "status":str(step.get("status","unknown")),
                   "continuity_task_id":str(step.get("continuity_task_id") or ""),
                   "verified":bool(verified),"approval_required":bool(approval_required)}
            self.world.set_entity("tasks",f"goal:{goal_id}:step:{step_id}",state,
                                  source="verified_goal_workflow",ttl_seconds=86400,
                                  confidence=1.0 if verified else 0.9)
        except Exception:
            # A secondary world projection cannot change the durable goal/continuity result.
            return

    def _task_for_step(self, goal_id, step):
        task_id=step.get("continuity_task_id")
        if task_id:
            task=self.continuity.get(task_id)
            if task:
                return task
        task=self.continuity.create(
            f"goal-step:{goal_id}:{step['id']}",
            next_action="Run this goal step through the verified runtime.",
        )
        self.goals.attach_continuity_task(goal_id,step['id'],task['task_id'])
        return task

    def _complete_from_checkpoint(self, goal_id, step, task):
        decision=self.continuity.resume(task['task_id'])
        if not decision.resumable or not decision.checkpoint:
            return {"status":"interrupted_needs_fresh_observation","verified":False,
                    "reason":decision.reason,"task_id":task['task_id']}
        state=decision.checkpoint.get('state',{})
        outcome={"verified":True,"verification_evidence":state.get("verification_evidence")}
        if not is_verified_action_outcome(outcome):
            return {"status":"interrupted_needs_fresh_observation","verified":False,
                    "reason":"checkpoint_evidence_invalid","task_id":task['task_id']}
        tools=state.get('tool_sequence',[])
        result="Verified after restart: "+", ".join(map(str,tools))
        self.goals.complete_step(goal_id,step['id'],result=result,success=True,verification=outcome)
        current=self.continuity.get(task['task_id'])
        if current and current['status']!='completed':
            self.continuity.set_status(task['task_id'],'completed')
        self._record_world_step(goal_id,step['id'],verified=True)
        return {"status":"completed","verified":True,"recovered_from_checkpoint":True,
                "goal_id":goal_id,"step_id":step['id'],"task_id":task['task_id']}

    def run_step(self, goal_id, step_id, *, user_approved=False):
        step=self.goals.get_step(goal_id,step_id)
        if step['status']=='running':
            task_id=step.get('continuity_task_id')
            task=self.continuity.get(task_id) if task_id else None
            if not task:
                return {"status":"interrupted_needs_fresh_observation","verified":False,
                        "reason":"running_step_has_no_continuity_checkpoint"}
            return self._complete_from_checkpoint(goal_id,step,task)
        task=self._task_for_step(goal_id,step)
        if step['status']=='completed':
            if task['status']!='completed': self.continuity.set_status(task['task_id'],'completed')
            return {"status":"completed","verified":True,"goal_id":goal_id,
                    "step_id":step_id,"task_id":task['task_id']}
        if step['status']!='pending':
            return {"status":step['status'],"verified":False,"goal_id":goal_id,
                    "step_id":step_id,"task_id":task['task_id']}

        if task['status'] in {'paused','failed'}:
            if task['status']=='failed':
                return {"status":"failed","verified":False,"task_id":task['task_id']}
            self.continuity.set_status(task['task_id'],'active',next_action="Run this goal step through the verified runtime.")
        step=self.goals.start_step(goal_id,step_id)
        self._record_world_step(goal_id,step_id)
        request=str(step.get('request') or step.get('title') or '').strip()
        if not request:
            self.goals.complete_step(goal_id,step_id,success=False,error='goal_step_request_missing')
            self.continuity.set_status(task['task_id'],'failed')
            self._record_world_step(goal_id,step_id)
            return {"status":"failed","verified":False,"reason":"goal_step_request_missing"}

        result=self.runtime.submit(request,source='approved-ui' if user_approved else 'goal_workflow')
        if result.get('status') in {'awaiting_approval','queued'}:
            reason=str(result.get('status'))
            self.goals.defer_step(goal_id,step_id,reason)
            self.continuity.set_status(task['task_id'],'paused',next_action='Explicit user approval is required before this step runs.')
            self._record_world_step(goal_id,step_id,approval_required=True)
            return {**result,"verified":False,"goal_id":goal_id,"step_id":step_id,"task_id":task['task_id']}

        if is_verified_action_outcome(result):
            evidence=result['verification_evidence']
            tools=result.get('verification_evidence',{}).get('verified_actions',[])
            tool_names=[row.get('tool','') for row in tools if isinstance(row,dict)]
            self.continuity.checkpoint(task['task_id'],label='verified_goal_step',verified=True,
                state={"goal_id":goal_id,"step_id":step_id,
                       "verification_evidence":evidence,"tool_sequence":tool_names})
            summary='Verified action postcondition passed: '+', '.join(tool_names)
            self.goals.complete_step(goal_id,step_id,result=summary,success=True,verification=result)
            self.continuity.set_status(task['task_id'],'completed')
            self._record_world_step(goal_id,step_id,verified=True)
            return {"status":"completed","verified":True,"goal_id":goal_id,
                    "step_id":step_id,"task_id":task['task_id'],
                    "result":result.get('result','')}

        state=str(result.get('completion_state') or result.get('status') or 'unverified')
        reason='Runtime returned without an independently verified mutation.'
        self.continuity.checkpoint(task['task_id'],label='unverified_goal_step',verified=False,
            state={"goal_id":goal_id,"step_id":step_id,"completion_state":state,
                   "tool_sequence":result.get('tool_sequence',[])})
        self.goals.complete_step(goal_id,step_id,success=False,error=reason)
        self.continuity.set_status(task['task_id'],'failed',next_action='Inspect current state before creating a new goal step; do not repeat automatically.')
        self._record_world_step(goal_id,step_id)
        return {"status":"failed_verification","verified":False,"goal_id":goal_id,
                "step_id":step_id,"task_id":task['task_id'],"reason":reason}
