
from __future__ import annotations
import json
from pathlib import Path
from .models import Experience, Workflow

class ExperienceStore:
    def __init__(self, path: str | Path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.experiences=[]
        self.workflows={}
        self._load()

    def record(self, exp: Experience):
        self.experiences.append(exp)
        key=(exp.task_type,exp.workflow)
        wf=self.workflows.setdefault(key,Workflow(*key))
        wf.record(exp.success)
        self._save()

    def best(self, task_type: str):
        choices=[w for (t,_),w in self.workflows.items() if t==task_type]
        return max(choices,key=lambda w:(w.promoted,w.confidence,w.successes),
                   default=None)

    def _save(self):
        data={
          "experiences":[e.__dict__ for e in self.experiences[-500:]],
          "workflows":[w.__dict__ for w in self.workflows.values()]
        }
        self.path.write_text(json.dumps(data,indent=2))

    def _load(self):
        if not self.path.exists(): return
        try:
            data=json.loads(self.path.read_text())
            for raw in data.get("experiences",[]):
                self.experiences.append(Experience(**raw))
            for raw in data.get("workflows",[]):
                w=Workflow(**raw)
                self.workflows[(w.task_type,w.workflow)]=w
        except Exception:
            self.experiences=[]; self.workflows={}
