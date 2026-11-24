"""Evidence-aware cross-domain transfer using semantic similarity + capabilities."""
from __future__ import annotations
from dataclasses import dataclass
import re
from .embeddings import EmbeddingEngine

_GROUPS=[
 {"document","report","word","docx","essay"},{"presentation","powerpoint","ppt","slides"},
 {"spreadsheet","excel","xlsx","table","data"},{"research","investigate","study","analyze"},
 {"code","coding","program","software","development"},{"android","phone","mobile","device"},
 {"web","browser","website","internet"},{"debug","repair","fix","resolve"},
 {"create","build","make","generate"},{"schedule","plan","calendar","deadline"},
 {"design","layout","visual","style"},{"optimize","optimization","efficient","performance"},
]
CANON={x:sorted(g)[0] for g in _GROUPS for x in g}
def tags(text): return {CANON.get(x,x) for x in re.findall(r"[a-z0-9]+",str(text).lower()) if len(x)>2}
@dataclass
class TransferCandidate:
    workflow:str; source_task:str; capability_overlap:float; semantic_similarity:float
    score:float; transferable:bool; rationale:str

class IntelligentTransfer:
    def __init__(self,store,engine=None,threshold=.28): self.store=store; self.engine=engine or EmbeddingEngine(); self.threshold=float(threshold)
    def find(self,task,limit=5):
        rows=[r for r in self.store.records if r.success]
        if not rows:return []
        enc=self.engine.encode([str(task)]+[r.task for r in rows]); target=tags(task); out=[]
        for i,r in enumerate(rows,1):
            src=tags(r.task); cap=len(target&src)/len(target|src) if target|src else 0
            sem=max(0,self.engine.cosine(enc.vectors[0],enc.vectors[i])); score=.55*sem+.45*cap
            transferable=bool(target&src) and score>=self.threshold
            if transferable:
                shared=", ".join(sorted(target&src)); out.append(TransferCandidate(r.workflow,r.task,round(cap,4),round(sem,4),round(score,4),True,f"shared capabilities: {shared}; semantic support: {sem:.3f}"))
        out.sort(key=lambda x:x.score,reverse=True); return out[:max(0,int(limit))]
