"""Cross-domain experience transfer with conservative capability matching."""
from __future__ import annotations
import re
from dataclasses import dataclass

_GROUPS=[
 {"document","report","word","docx","essay"},
 {"presentation","powerpoint","ppt","slides"},
 {"spreadsheet","excel","xlsx","table","data"},
 {"research","investigate","study","analyze"},
 {"code","coding","program","software","development"},
 {"android","phone","mobile","device"},
 {"web","browser","website","internet"},
 {"debug","repair","fix","resolve"},
 {"create","build","make","generate"},
]
CANON={x:sorted(g)[0] for g in _GROUPS for x in g}

def tags(text):
    return {CANON.get(x,x) for x in re.findall(r"[a-z0-9]+",str(text).lower()) if len(x)>2}

@dataclass
class TransferCandidate:
    workflow:str
    source_task:str
    overlap:float
    transferable:bool
    rationale:str

class ExperienceTransfer:
    def __init__(self, store, threshold=.25):
        self.store=store; self.threshold=float(threshold)
    def find(self, task, limit=5):
        target=tags(task); out=[]
        for r in self.store.records:
            if not r.success: continue
            source=tags(r.task)
            overlap=len(target&source)/len(target|source) if target|source else 0
            shared=sorted(target&source)
            transferable=overlap>=self.threshold and bool(shared)
            if transferable:
                rationale=f"shared capabilities: {', '.join(shared)}"
                out.append(TransferCandidate(r.workflow,r.task,round(overlap,4),True,rationale))
        out.sort(key=lambda x:x.overlap,reverse=True)
        return out[:max(0,int(limit))]
    def best(self, task):
        xs=self.find(task,1)
        return xs[0] if xs else None
