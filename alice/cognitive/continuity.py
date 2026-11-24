from __future__ import annotations
"""ALICE v3.52 verified executive continuity.

Converts persistent long-horizon state into a bounded next-step recommendation.
It never performs the recommended action and never marks progress complete
without explicit verified evidence.
"""
from dataclasses import dataclass, asdict
from typing import Any
from .long_horizon import LongHorizonStore

@dataclass
class ContinuityDecision:
    goal: dict[str, Any] | None
    next_action: str | None
    blocking_dependencies: list[str]
    resume_reason: str
    completion_verified: bool = False
    status_change: str | None = None

class ExecutiveContinuity:
    VERSION='v3.52.0'
    def __init__(self, goals: LongHorizonStore): self.goals=goals
    def resume(self, request: str, limit=4):
        matches=self.goals.find(request,limit=limit)
        if not matches: return ContinuityDecision(None,None,[],"no_related_goal")
        g=matches[0]
        pending=[m for m in g.get('milestones',[]) if m not in g.get('completed_milestones',[])]
        action=(g.get('next_actions') or [None])[0]
        reason='matched_persistent_goal'
        if pending: reason='matched_goal_with_pending_milestones'
        return ContinuityDecision(g,action,list(g.get('dependencies') or []),reason)
    def record_verified_outcome(self, goal_id: str, *, outcome: str, success: bool, evidence: str):
        if not str(evidence).strip(): raise ValueError('verified evidence is required')
        g=self.goals.get(goal_id)
        if not g: raise KeyError(f'Unknown goal: {goal_id}')
        self.goals.update(goal_id,last_outcome=str(outcome)[:2000])
        if success:
            return self.goals.update(goal_id,evidence=list(g.get('evidence',[]))+[str(evidence)[:1000]])
        return self.goals.record_failure(goal_id,f'{outcome} | evidence: {evidence}')
    def complete_goal(self, goal_id: str, *, evidence: str):
        if not str(evidence).strip(): raise ValueError('verified evidence is required')
        g=self.goals.get(goal_id)
        if not g: raise KeyError(f'Unknown goal: {goal_id}')
        pending=[m for m in g.get('milestones',[]) if m not in g.get('completed_milestones',[])]
        if pending: raise ValueError('cannot complete goal while milestones remain unverified')
        return self.goals.update(goal_id,status='completed',last_outcome='completed with verified evidence: '+str(evidence)[:1000])
