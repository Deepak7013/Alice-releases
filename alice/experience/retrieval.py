
"""Evidence-aware experience retrieval."""
from __future__ import annotations
from dataclasses import dataclass
import math

@dataclass
class RetrievalResult:
    workflow: str
    similarity: float
    reliability: float
    score: float
    evidence: dict
    source: str

class ExperienceRetriever:
    def __init__(self, store, min_similarity=0.35):
        self.store=store; self.min_similarity=float(min_similarity)

    def search(self, task, limit=5):
        candidates=self.store.recall(task,limit=max(limit*4,20))
        out=[]
        for c in candidates:
            e=c["experience"]
            sim=float(c["similarity"])
            evidence=e.get("evidence") or {}
            # Evidence signals are bounded and cannot create authority.
            verified=1.0 if evidence.get("verified") or evidence.get("ok") else 0.0
            quality=float(evidence.get("quality",0) or 0)
            quality=max(0.0,min(1.0,quality))
            reliability=min(1.0,0.5+0.25*verified+0.25*quality)
            score=sim*(0.65+0.35*reliability)
            if sim>=self.min_similarity:
                out.append(RetrievalResult(e["workflow"],round(sim,3),
                    round(reliability,3),round(score,3),evidence,"global_experience"))
        out.sort(key=lambda x:x.score,reverse=True)
        return out[:max(0,int(limit))]
