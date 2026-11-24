
"""Adds reusable experience hints to plans without changing authority or risk."""
from __future__ import annotations
from .planner import GoalPlanner

class ExperienceAwarePlanner:
    def __init__(self, experience_gateway, base=None):
        self.gateway=experience_gateway
        self.base=base or GoalPlanner()

    def plan(self, goal):
        plan=self.base.plan(goal)
        choice=self.gateway.choose(goal.text if hasattr(goal,"text") else str(goal))
        if choice.selected:
            plan.assumptions.append(f"Reusable workflow candidate: {choice.selected} (confidence {choice.confidence:.3f}).")
            plan.assumptions.append("Reuse is advisory only; existing approval, execution, and verification gates remain authoritative.")
        else:
            plan.assumptions.append("No sufficiently reliable prior workflow was reused.")
        return plan
