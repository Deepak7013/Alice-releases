"""Unified adaptive intelligence facade for semantic memory, transfer and algorithms."""
from __future__ import annotations
from .embeddings import EmbeddingEngine
from .semantic_memory import NeuralSemanticMemory
from .transfer import IntelligentTransfer
from .algorithms import AlgorithmAdvisor
from .efficiency import EfficiencyPolicy

class IntelligenceBrain:
    def __init__(self,experience_store,embedding_backend="auto"):
        self.engine=EmbeddingEngine(embedding_backend)
        self.semantic=NeuralSemanticMemory(experience_store,self.engine)
        self.transfer=IntelligentTransfer(experience_store,self.engine)
        self.algorithms=AlgorithmAdvisor()
        self.efficiency=EfficiencyPolicy()
    def solve_strategy(self,task,objective=None,data=None,constraints=None):
        direct=self.semantic.search(task,limit=3)
        if direct and direct[0].confidence>=.45:
            d=self.efficiency.choose(direct_confidence=direct[0].confidence,deterministic_available=True)
            return {"strategy":"reuse_direct_experience","confidence":direct[0].confidence,
                    "experience":direct[0].experience.workflow,"source":direct[0].backend,"efficiency":d.path}
        transferred=self.transfer.find(task,limit=3)
        if transferred and transferred[0].score>=.42:
            d=self.efficiency.choose(transfer_confidence=transferred[0].score,deterministic_available=True)
            return {"strategy":"transfer_experience","confidence":transferred[0].score,
                    "experience":transferred[0].workflow,"source":"semantic_capability_transfer","efficiency":d.path}
        alg=self.algorithms.recommend(objective or task,data=data,constraints=constraints,top_k=3)
        d=self.efficiency.choose(deterministic_available=bool(alg),complexity="normal")
        return {"strategy":"select_algorithm","confidence":round(min(1.0,(alg[0]["score"] if alg else 0)/5),4),"algorithms":alg,"source":"algorithm_advisor","efficiency":d.path}
