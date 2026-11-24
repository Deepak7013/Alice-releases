import secrets
from .models import Workflow, WorkflowStep, WorkflowStatus
class WorkflowEngine:
    def __init__(self): self._workflows={}
    def create(self,name,steps):
        if not name.strip(): raise ValueError('workflow name is required')
        ids={s.step_id for s in steps}
        if len(ids)!=len(steps): raise ValueError('duplicate step id')
        for s in steps:
            if s.step_id in s.depends_on or any(d not in ids for d in s.depends_on): raise ValueError('invalid dependency')
        w=Workflow(secrets.token_hex(8),name.strip(),steps,WorkflowStatus.READY); self._workflows[w.workflow_id]=w; return w
    def runnable(self,w):
        done={s.step_id for s in w.steps if s.status=='completed'}
        return [s for s in w.steps if s.status=='pending' and all(d in done for d in s.depends_on)]
    def run(self,w,executor):
        w.status=WorkflowStatus.RUNNING
        while True:
            ready=self.runnable(w)
            if not ready: break
            for s in ready:
                try: s.result=executor(s); s.status='completed'
                except Exception as e: s.error=str(e); s.status='failed'; w.status=WorkflowStatus.FAILED; return w
        w.status=WorkflowStatus.COMPLETED if all(s.status=='completed' for s in w.steps) else WorkflowStatus.PAUSED
        return w
