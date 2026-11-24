
from __future__ import annotations
from .models import LearningDecision
from .store import ExperienceStore

class SkillRefiner:
    """Promotes proven procedures without changing authority.

    Promotion only affects workflow preference. It never grants permissions,
    modifies protected source, or bypasses safety/approval gates.
    """
    def __init__(self, store: ExperienceStore,
                 min_attempts=3, promote_confidence=0.80,
                 demote_confidence=0.55, max_regressions=2):
        self.store=store
        self.min_attempts=min_attempts
        self.promote_confidence=promote_confidence
        self.demote_confidence=demote_confidence
        self.max_regressions=max_regressions

    def evaluate(self, task_type, workflow) -> LearningDecision:
        wf=self.store.workflows.get((task_type,workflow))
        if wf is None:
            return LearningDecision("ignore", None, "no evidence")  # type: ignore

        if (not wf.promoted and wf.attempts >= self.min_attempts
                and wf.confidence >= self.promote_confidence):
            wf.promoted=True
            self.store._save()
            return LearningDecision("promote",wf,"sufficient successful evidence")

        if (wf.promoted and
                (wf.confidence < self.demote_confidence
                 or wf.regression_count >= self.max_regressions)):
            wf.promoted=False
            self.store._save()
            return LearningDecision("demote",wf,"workflow regression detected")

        return LearningDecision("keep",wf,"no promotion/demotion threshold crossed")
