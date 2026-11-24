"""Controlled initiative policy. Agency never expands Alice's authority."""
from __future__ import annotations
from .models import Initiative, InitiativeDecision, Goal

class AgencyPolicy:
    CONSEQUENTIAL_WORDS=("send","delete","purchase","buy","pay","transfer","publish","post","message","email","install","uninstall","submit","approve","login")
    def decide(self, goal: Goal, observation=None):
        obs=observation or {}
        event=str(obs.get("event","")).lower()
        payload=str(obs.get("payload",{})).lower()
        evidence=[event] if event else []
        # A goal that has no evidence to act on should wait rather than invent work.
        if goal.status != "ACTIVE":
            return InitiativeDecision(Initiative.WAIT,"Goal is not active",goal.id,False,1.0,evidence)
        text=(goal.title+" "+goal.description).lower()
        if event in {"deadline_approaching","goal_blocked","new_information"}:
            return InitiativeDecision(Initiative.RESEARCH,"New information may change the plan",goal.id,False,0.86,evidence)
        if event in {"task_failed","verification_failed"}:
            return InitiativeDecision(Initiative.PLAN,"Failure requires replanning before another action",goal.id,False,0.9,evidence)
        if event in {"goal_progress","task_completed"}:
            return InitiativeDecision(Initiative.OBSERVE,"Refresh state before deciding the next step",goal.id,False,0.82,evidence)
        if any(w in text or w in payload for w in self.CONSEQUENTIAL_WORDS):
            return InitiativeDecision(Initiative.RECOMMEND,"Goal may require a consequential action; prepare a recommendation first",goal.id,True,0.75,evidence)
        if goal.progress <= 0:
            return InitiativeDecision(Initiative.PLAN,"Active goal needs an explicit next-step plan",goal.id,False,0.8,evidence)
        return InitiativeDecision(Initiative.OBSERVE,"No sufficiently strong trigger for autonomous action",goal.id,False,0.7,evidence)
