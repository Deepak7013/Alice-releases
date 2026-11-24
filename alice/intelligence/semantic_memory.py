"""Neural-first semantic memory retrieval with provenance and confidence."""
from __future__ import annotations
from dataclasses import dataclass
from .embeddings import EmbeddingEngine

@dataclass
class SemanticMemoryMatch:
    experience: object
    similarity: float
    backend: str
    confidence: float
    explanation: str

class NeuralSemanticMemory:
    def __init__(self, store, engine=None, minimum=0.18):
        self.store=store
        self.engine=engine or EmbeddingEngine()
        self.minimum=float(minimum)

    def search(self, task, limit=5):
        records=[r for r in self.store.records if r.success]
        if not records: return []
        texts=[r.task for r in records]
        encoded=self.engine.encode([str(task)]+texts)
        q=encoded.vectors[0]
        rows=[]
        for i,r in enumerate(records,1):
            sim=max(-1.0,min(1.0,self.engine.cosine(q,encoded.vectors[i])))
            evidence=r.evidence or {}
            verified=1.0 if evidence.get("verified") or evidence.get("ok") else 0.0
            quality=max(0.0,min(1.0,float(evidence.get("quality",0) or 0)))
            confidence=max(0.0,min(1.0,0.45*max(0,sim)+0.25*verified+0.30*quality))
            if sim>=self.minimum:
                rows.append(SemanticMemoryMatch(r,round(sim,4),encoded.backend,round(confidence,4),
                    f"semantic similarity={sim:.3f}; verified={bool(verified)}; quality={quality:.3f}"))
        rows.sort(key=lambda x:(x.confidence,x.similarity),reverse=True)
        return rows[:max(0,int(limit))]
