
"""Conservative workflow optimizer based on verified historical outcomes."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class Optimization:
    selected: str | None
    confidence: float
    alternatives: list
    reason: str

class WorkflowOptimizer:
    def __init__(self,retriever,confidence_floor=0.55):
        self.retriever=retriever; self.confidence_floor=float(confidence_floor)

    def choose(self,task):
        results=self.retriever.search(task,limit=5)
        if not results:
            return Optimization(None,0.0,[],"no verified reusable workflow")
        best=results[0]
        confidence=max(0.0,min(1.0,best.score))
        if confidence<self.confidence_floor:
            return Optimization(None,confidence,
                                [r.workflow for r in results],
                                "evidence below reuse threshold")
        return Optimization(best.workflow,confidence,
                            [r.workflow for r in results[1:]],
                            "selected highest evidence-weighted workflow")
