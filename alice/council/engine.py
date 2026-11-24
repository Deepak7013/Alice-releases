from __future__ import annotations
import hashlib,time
class CouncilEngine:
    """Bounded multi-perspective reasoning coordinator.

    It creates independent proposals from supplied callable roles and returns
    an auditable consensus object. It never executes actions or grants access.
    """
    VERSION='v3.26.0'
    def __init__(self,roles=None): self.roles=dict(roles or {})
    def register(self,name,fn):
        if not callable(fn): raise TypeError('role must be callable')
        self.roles[str(name)[:80]]=fn; return sorted(self.roles)
    def deliberate(self,task,required=2):
        names=list(self.roles)[:max(1,int(required))]
        proposals=[]
        for n in names:
            try: proposals.append({'role':n,'ok':True,'proposal':self.roles[n](task)})
            except Exception as e: proposals.append({'role':n,'ok':False,'error':str(e)[:500]})
        good=[p for p in proposals if p['ok']]
        digest=hashlib.sha256(repr([(p['role'],p.get('proposal')) for p in good]).encode()).hexdigest()[:16]
        return {'version':self.VERSION,'task':str(task)[:2000],'proposals':proposals,'consensus':good[0]['proposal'] if len(good)==1 else None,'agreement':len(good)/max(1,len(proposals)),'digest':digest,'created_at':time.time(),'requires_verification':True}
