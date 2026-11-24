from __future__ import annotations
"""ALICE v3.51 long-horizon executive memory.

Stores durable goals separately from conversational history so ALICE can resume
multi-session work from verified milestones instead of treating every prompt as
an isolated task. This module stores state only; it never executes actions.
"""
from dataclasses import dataclass, asdict, field
from pathlib import Path
import json, time, uuid

@dataclass
class LongGoal:
    goal_id: str
    title: str
    objective: str
    status: str = "active"
    milestones: list[str] = field(default_factory=list)
    completed_milestones: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    last_outcome: str = ""
    updated_at: float = field(default_factory=time.time)

class LongHorizonStore:
    VERSION="v3.51.0"
    VALID_STATUS={"active","paused","completed","failed","cancelled"}
    def __init__(self, root=None, path=None, max_goals=64):
        self.root=Path(root or Path(__file__).resolve().parents[2]).resolve()
        self.path=Path(path) if path else self.root/'alice_workspace'/'long_horizon_goals.json'
        self.path.parent.mkdir(parents=True,exist_ok=True); self.max_goals=max(1,int(max_goals)); self.goals={}; self._load()
    def _load(self):
        if not self.path.exists(): return
        try:
            raw=json.loads(self.path.read_text(encoding='utf-8'))
            self.goals={k:LongGoal(**v) for k,v in raw.items() if isinstance(v,dict)}
        except (OSError,ValueError,TypeError): self.goals={}
    def _save(self):
        items=sorted(self.goals.values(),key=lambda x:x.updated_at,reverse=True)[:self.max_goals]
        self.goals={x.goal_id:x for x in items}
        tmp=self.path.with_suffix('.tmp'); tmp.write_text(json.dumps({k:asdict(v) for k,v in self.goals.items()},indent=2,ensure_ascii=False),encoding='utf-8'); tmp.replace(self.path)
    @staticmethod
    def _clean(values,limit=64): return [str(x).strip()[:1000] for x in (values or []) if str(x).strip()][:limit]
    def create(self,title,objective,*,milestones=None,dependencies=None,next_actions=None):
        title=str(title).strip(); objective=str(objective).strip()
        if not title or not objective: raise ValueError('title and objective are required')
        g=LongGoal('lg_'+uuid.uuid4().hex[:16],title,objective,milestones=self._clean(milestones),dependencies=self._clean(dependencies),next_actions=self._clean(next_actions))
        self.goals[g.goal_id]=g; self._save(); return self.get(g.goal_id)
    def get(self,goal_id):
        g=self.goals.get(str(goal_id)); return asdict(g) if g else None
    def active(self): return [asdict(g) for g in sorted(self.goals.values(),key=lambda x:x.updated_at,reverse=True) if g.status=='active']
    def find(self,text,limit=8):
        q=str(text).lower(); hits=[]
        for g in self.goals.values():
            hay=f'{g.title} {g.objective} {' '.join(g.next_actions)}'.lower()
            if any(t in hay for t in q.split() if len(t)>2): hits.append(g)
        return [asdict(g) for g in sorted(hits,key=lambda x:x.updated_at,reverse=True)[:max(1,int(limit))]]
    def update(self,goal_id,**changes):
        g=self.goals.get(str(goal_id))
        if not g: raise KeyError(f'Unknown goal: {goal_id}')
        if 'status' in changes and changes['status'] not in self.VALID_STATUS: raise ValueError('Invalid goal status')
        for k,v in changes.items():
            if k not in g.__dataclass_fields__: raise ValueError(f'Unknown goal field: {k}')
            setattr(g,k,self._clean(v) if k in {'milestones','completed_milestones','dependencies','next_actions','evidence','failures'} else str(v)[:2000] if isinstance(v,str) else v)
        g.updated_at=time.time(); self._save(); return self.get(g.goal_id)
    def milestone(self,goal_id,name,evidence=''):
        g=self.goals.get(str(goal_id));
        if not g: raise KeyError(f'Unknown goal: {goal_id}')
        name=str(name).strip()
        if name and name not in g.milestones: g.milestones.append(name)
        if name and name not in g.completed_milestones: g.completed_milestones.append(name)
        if evidence: g.evidence.append(str(evidence)[:1000])
        g.updated_at=time.time(); self._save(); return self.get(goal_id)
    def record_failure(self,goal_id,failure):
        g=self.goals.get(str(goal_id));
        if not g: raise KeyError(f'Unknown goal: {goal_id}')
        g.failures.append(str(failure)[:1000]); g.last_outcome='failure: '+str(failure)[:1000]; g.updated_at=time.time(); self._save(); return self.get(goal_id)
