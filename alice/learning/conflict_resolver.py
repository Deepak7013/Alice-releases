from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

@dataclass(frozen=True)
class LearningConflict:
    topic: str
    existing: str
    incoming: str
    decision: str
    reason: str

class LearningConflictResolver:
    """Deterministic, non-destructive resolver for contradictory learned claims."""
    def resolve(self, topic: str, existing: str, incoming: str, *, existing_confidence=0.0, incoming_confidence=0.0):
        topic=str(topic).strip(); existing=str(existing).strip(); incoming=str(incoming).strip()
        if not topic or not incoming: raise ValueError('topic and incoming claim are required')
        if not existing: return LearningConflict(topic, existing, incoming, 'accept', 'no existing claim')
        if existing == incoming: return LearningConflict(topic, existing, incoming, 'duplicate', 'claims are identical')
        ec=float(existing_confidence); ic=float(incoming_confidence)
        if ic > ec: return LearningConflict(topic, existing, incoming, 'supersede', 'incoming confidence is higher')
        if ec > ic: return LearningConflict(topic, existing, incoming, 'retain', 'existing confidence is higher')
        return LearningConflict(topic, existing, incoming, 'review', 'confidence is tied; human review required')
