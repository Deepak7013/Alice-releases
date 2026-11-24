
from __future__ import annotations
from alice.acquisition.pipeline import CapabilityPromotionPipeline

class LearnedSkillPromoter:
    def __init__(self, store, pipeline: CapabilityPromotionPipeline):
        self.store=store
        self.pipeline=pipeline

    def propose_best(self, task_type):
        wf=self.store.best(task_type)
        if wf is None or not wf.promoted:
            return None
        return self.pipeline.propose(
            wf.workflow, task_type, wf.confidence,
            scopes=[], evidence=[{
                "attempts":wf.attempts,
                "successes":wf.successes,
                "failures":wf.failures
            }]
        )
