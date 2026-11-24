"""Alice's controlled agency engine: goals + observations + initiative decisions."""
from __future__ import annotations
from .models import Goal, GoalStatus, Observation
from .store import AgencyStore
from .policy import AgencyPolicy

class AgencyEngine:
    def __init__(self, root=None, runtime=None, policy=None):
        self.store=AgencyStore(root); self.runtime=runtime; self.policy=policy or AgencyPolicy()
    def create_goal(self,title,description="",priority=50,constraints=None):
        goal=Goal.create(title,description,priority,constraints)
        self.store.put_goal(goal)
        if self.runtime: self.runtime.audit.record("agency.goal_created",goal=goal.to_dict())
        return goal.to_dict()
    def update_goal(self,goal_id,**changes):
        raw=self.store.get_goal(goal_id)
        if not raw: raise KeyError(goal_id)
        allowed={"title","description","priority","status","constraints","progress"}
        for k,v in changes.items():
            if k in allowed: raw[k]=v
        import time; raw["updated_at"]=time.time()
        # Rehydrate minimally to preserve model contract.
        goal=Goal(**raw); self.store.put_goal(goal)
        return goal.to_dict()
    def observe(self,event,payload=None,source="system"):
        obs=Observation(event,payload or {},source=source); self.store.add_observation(obs)
        decisions=[]
        for raw in self.store.goals(status=GoalStatus.ACTIVE):
            goal=Goal(**raw); decision=self.policy.decide(goal,obs.__dict__); decisions.append(decision.to_dict())
        if self.runtime: self.runtime.events.publish("agency.observed",{"event":event,"decisions":decisions})
        return decisions
    def decide_for_goal(self,goal_id,observation=None):
        raw=self.store.get_goal(goal_id)
        if not raw: raise KeyError(goal_id)
        return self.policy.decide(Goal(**raw),observation).to_dict()
    def active_goals(self): return self.store.goals(status=GoalStatus.ACTIVE)
    def recent_observations(self,limit=50): return self.store.observations(limit)
