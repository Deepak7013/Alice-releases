from __future__ import annotations
from dataclasses import dataclass,asdict
from alice.learning.intake import LearningIntake
from alice.learning.provenance import LearningProvenance
import hashlib

@dataclass(frozen=True)
class GovernedLearningResult:
    accepted:bool; reason:str; topic:str=''; fingerprint:str=''; persisted:bool=False
    def as_dict(self): return asdict(self)

class GovernedLearning:
    """Single local gate joining learning intake and provenance.
    It deliberately does not write the knowledge store itself; callers can
    persist only after the deterministic decision is accepted.
    """
    def __init__(self,root=None): self.intake=LearningIntake(); self.provenance=LearningProvenance(root)
    def evaluate(self,text):
        d=self.intake.decide(text)
        if not d.accepted:return GovernedLearningResult(False,d.reason)
        if self.provenance.seen(hashlib.sha256(' '.join(str(text).split()).lower().encode()).hexdigest()): return GovernedLearningResult(False,'duplicate',d.topic,d.fingerprint,False)
        self.provenance.record(d.text,d.topic,confidence=d.confidence)
        return GovernedLearningResult(True,d.reason,d.topic,d.fingerprint,True)
