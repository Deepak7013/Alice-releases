from __future__ import annotations
import hashlib, json, time
from pathlib import Path
from .models import Goal, GoalStep, GoalStatus

class GoalEngine:
    """Persistent, dependency-aware goal manager.

    This layer plans and tracks work but never silently executes it. Execution
    remains owned by ALICE's Action/Runtime permission stack.
    """
    VERSION = "v3.20.0"
    def __init__(self, root=None):
        self.root = Path(root or Path(__file__).resolve().parents[2])
        self.path = self.root / "alice_workspace" / "goals" / "goals.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()
    def _load(self):
        try:
            d=json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(d,dict):
                d.setdefault("goals",[]); d.setdefault("events",[]); return d
        except Exception: pass
        return {"goals":[],"events":[]}
    def _save(self):
        tmp=self.path.with_suffix('.tmp'); tmp.write_text(json.dumps(self.data,indent=2,ensure_ascii=False),encoding='utf-8'); tmp.replace(self.path)
    @staticmethod
    def _id(title, objective):
        return hashlib.sha256((str(title).strip().lower()+"|"+str(objective).strip().lower()).encode()).hexdigest()[:16]
    def create(self,title,objective,priority=.5,deadline=None,tags=None):
        gid=self._id(title,objective)
        existing=next((x for x in self.data['goals'] if x['id']==gid),None)
        if existing: return existing
        g=Goal(gid,str(title)[:200],str(objective)[:2000],priority=max(0,min(1,float(priority))),deadline=deadline,tags=list(tags or [])[:20])
        self.data['goals'].append(g.to_dict()); self._event(gid,'created'); self._save(); return g.to_dict()
    def _goal(self,gid):
        return next((g for g in self.data['goals'] if g['id']==gid),None)
    def get_step(self,gid,sid):
        goal=self._goal(gid)
        if not goal: raise KeyError(gid)
        step=next((x for x in goal['steps'] if x['id']==sid),None)
        if not step: raise KeyError(sid)
        return dict(step)
    def add_step(self,gid,title,request='',depends_on=None,step_id=None):
        g=self._goal(gid)
        if not g: raise KeyError(gid)
        sid=step_id or hashlib.sha256(f"{gid}|{title}|{len(g['steps'])}".encode()).hexdigest()[:12]
        deps=list(depends_on or [])
        known={s['id'] for s in g['steps']}
        if any(d not in known for d in deps): raise ValueError('Unknown step dependency')
        if any(s['id']==sid for s in g['steps']): return next(s for s in g['steps'] if s['id']==sid)
        s=GoalStep(sid,str(title)[:200],str(request)[:2000],depends_on=deps)
        g['steps'].append(s.__dict__); g['updated_at']=time.time(); self._event(gid,'step_added',sid); self._save(); return s.__dict__
    def ready_steps(self,gid):
        g=self._goal(gid)
        if not g or g['status']!=GoalStatus.ACTIVE.value: return []
        done={s['id'] for s in g['steps'] if s['status']=='completed'}
        return [s for s in g['steps'] if s['status']=='pending' and all(d in done for d in s.get('depends_on',[]))]
    def start_step(self,gid,sid):
        g=self._goal(gid); s=next((x for x in (g or {}).get('steps',[]) if x['id']==sid),None)
        if not s: raise KeyError(sid)
        if s not in self.ready_steps(gid): raise ValueError('Step is not ready')
        s['status']='running'; s['attempts']+=1; s['updated_at']=time.time(); g['updated_at']=time.time(); self._event(gid,'step_started',sid); self._save(); return dict(s)
    def attach_continuity_task(self,gid,sid,task_id):
        goal=self._goal(gid)
        if not goal: raise KeyError(gid)
        step=next((x for x in goal['steps'] if x['id']==sid),None)
        if not step: raise KeyError(sid)
        current=step.get('continuity_task_id')
        if current and current!=task_id: raise ValueError('A continuity task is already attached to this goal step')
        step['continuity_task_id']=str(task_id); goal['updated_at']=time.time()
        self._save(); return dict(step)
    def defer_step(self,gid,sid,reason=''):
        goal=self._goal(gid)
        if not goal: raise KeyError(gid)
        step=next((x for x in goal['steps'] if x['id']==sid),None)
        if not step: raise KeyError(sid)
        if step['status']!='running': raise ValueError('Only a running step can be deferred')
        step['status']='pending'; step['last_error']=str(reason)[:1000]
        step['updated_at']=time.time(); goal['updated_at']=time.time()
        self._event(gid,'step_deferred',sid); self._save(); return dict(step)
    def complete_step(self,gid,sid,result='',success=True,error='',verification=None):
        if success:
            from ..runtime.outcomes import is_verified_action_outcome
            if not is_verified_action_outcome(verification):
                raise ValueError('Goal steps require an independently verified action outcome')
        g=self._goal(gid); s=next((x for x in (g or {}).get('steps',[]) if x['id']==sid),None)
        if not s: raise KeyError(sid)
        if success and s['status']!='running': raise ValueError('Only a running goal step can be completed')
        if success:
            done={x['id'] for x in g['steps'] if x['status']=='completed'}
            if any(dep not in done for dep in s.get('depends_on',[])):
                raise ValueError('Goal step dependencies are not complete')
        s['status']='completed' if success else 'failed'; s['result']=str(result)[:3000]; s['last_error']=str(error)[:1000]; s['updated_at']=time.time(); g['updated_at']=time.time()
        if success: s['verification_evidence']=verification['verification_evidence']
        if success and g['steps'] and all(x['status']=='completed' for x in g['steps']): g['status']=GoalStatus.COMPLETED.value
        if not success: g['status']=GoalStatus.FAILED.value
        self._event(gid,'step_completed' if success else 'step_failed',sid); self._save(); return dict(g)
    def pause(self,gid): return self._set_status(gid,GoalStatus.PAUSED.value)
    def resume(self,gid): return self._set_status(gid,GoalStatus.ACTIVE.value)
    def cancel(self,gid): return self._set_status(gid,GoalStatus.CANCELLED.value)
    def _set_status(self,gid,status):
        g=self._goal(gid)
        if not g: raise KeyError(gid)
        g['status']=status; g['updated_at']=time.time(); self._event(gid,'status',status); self._save(); return dict(g)
    def status(self,gid):
        g=self._goal(gid)
        if not g: raise KeyError(gid)
        remaining=sum(1 for s in g['steps'] if s['status']!='completed')
        overdue=bool(g.get('deadline') and time.time()>g['deadline'] and g['status']==GoalStatus.ACTIVE.value)
        return {'goal':dict(g),'ready_steps':self.ready_steps(gid),'remaining_steps':remaining,'overdue':overdue}
    def list_active(self): return [dict(g) for g in self.data['goals'] if g['status'] in (GoalStatus.ACTIVE.value,GoalStatus.PAUSED.value)]
    def _event(self,gid,kind,value=''): self.data['events']= (self.data.get('events',[])+[{'goal_id':gid,'kind':kind,'value':value,'at':time.time()}])[-2000:]
