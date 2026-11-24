
"""Single interface for Alice to remember and reuse verified task experience."""
from __future__ import annotations
from .global_store import GlobalExperienceStore
from .retrieval import ExperienceRetriever
from .optimizer import WorkflowOptimizer

class ExperienceGateway:
    def __init__(self, root=None):
        self.store=GlobalExperienceStore(root)
        self.retriever=ExperienceRetriever(self.store)
        self.optimizer=WorkflowOptimizer(self.retriever)

    def remember(self, task, workflow, success, *, duration_ms=0, evidence=None, tools=None, context=None):
        return self.store.record(task,workflow,success,duration_ms=duration_ms,
                                 evidence=evidence,tools=tools,context=context)

    def recommend(self, task, limit=5):
        return self.retriever.search(task,limit=limit)

    def choose(self, task):
        return self.optimizer.choose(task)

    def stats(self):
        return self.store.stats()
