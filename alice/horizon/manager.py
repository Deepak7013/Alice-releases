from __future__ import annotations
import hashlib,json,time
from pathlib import Path
class HorizonManager:
    VERSION='v3.21.0'
    def __init__(self,root=None):
        self.root=Path(root or Path(__file__).resolve().parents[2]); self.path=self.root/'alice_workspace'/'horizon'/'plans.json'; self.path.parent.mkdir(parents=True,exist_ok=True); self.data=self._load()
    def _load(self):
        try:
            d=json.loads(self.path.read_text(encoding='utf-8'))
            if isinstance(d,dict): d.setdefault('plans',[]); return d
        except Exception: pass
        return {'plans':[]}
    def _save(self):
        t=self.path.with_suffix('.tmp'); t.write_text(json.dumps(self.data,indent=2),encoding='utf-8'); t.replace(self.path)
    def create(self,goal_id,checkpoint_limit=25):
        pid=hashlib.sha256(str(goal_id).encode()).hexdigest()[:16]
        p=next((x for x in self.data['plans'] if x['id']==pid),None)
        if p:return p
        p={'id':pid,'goal_id':str(goal_id),'status':'active','checkpoints':[],'checkpoint_limit':max(1,min(100,int(checkpoint_limit))),'created_at':time.time(),'updated_at':time.time()}; self.data['plans'].append(p); self._save(); return p
    def checkpoint(self,plan_id,label,state,verified=False):
        p=next((x for x in self.data['plans'] if x['id']==plan_id),None)
        if not p: raise KeyError(plan_id)
        cp={'id':hashlib.sha256(f"{plan_id}|{label}|{len(p['checkpoints'])}".encode()).hexdigest()[:12],'label':str(label)[:200],'state':state,'verified':bool(verified),'at':time.time()}
        p['checkpoints'].append(cp); p['checkpoints']=p['checkpoints'][-p['checkpoint_limit']:]; p['updated_at']=time.time(); self._save(); return cp
    def latest_verified(self,plan_id):
        p=next((x for x in self.data['plans'] if x['id']==plan_id),None)
        if not p: raise KeyError(plan_id)
        rows=[x for x in p['checkpoints'] if x.get('verified')]; return rows[-1] if rows else None
    def recover(self,plan_id):
        cp=self.latest_verified(plan_id)
        if not cp: raise RuntimeError('No verified checkpoint available')
        return {'recovery_available':True,'checkpoint':cp,'requires_executor_verification':True}
    def complete(self,plan_id):
        p=next((x for x in self.data['plans'] if x['id']==plan_id),None)
        if not p: raise KeyError(plan_id)
        p['status']='completed'; p['updated_at']=time.time(); self._save(); return dict(p)
