"""Semantic retrieval adapter that augments Alice's existing experience retrieval."""
from __future__ import annotations
from .semantic import SemanticExperienceIndex

class SemanticExperienceRetriever:
    def __init__(self, store, minimum=0.12):
        self.store=store
        self.minimum=float(minimum)

    def search(self, task, limit=5):
        records=[r for r in self.store.records if r.success]
        idx=SemanticExperienceIndex(records)
        out=[]
        for m in idx.search(task,limit=max(1,int(limit)*3),minimum=self.minimum):
            r=records[m.index]
            evidence=r.evidence or {}
            verified=1.0 if evidence.get("verified") or evidence.get("ok") else 0.0
            quality=max(0.0,min(1.0,float(evidence.get("quality",0) or 0)))
            reliability=min(1.0,0.5+0.25*verified+0.25*quality)
            score=m.similarity*(0.65+0.35*reliability)
            out.append({
                "workflow":r.workflow,"similarity":m.similarity,
                "score":round(score,4),"reliability":round(reliability,4),
                "evidence":evidence,"explanation":idx.explain(task,m.index),
            })
        out.sort(key=lambda x:x["score"],reverse=True)
        return out[:max(0,int(limit))]
