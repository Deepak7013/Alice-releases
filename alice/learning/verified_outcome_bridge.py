"""Turn verified action outcomes into governed, replayable learning records.

The bridge never grants authority and never treats execution alone as success.
Only a verification envelope marked verified may become a positive lesson.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from time import time
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class OutcomeLesson:
    action_id: str
    outcome: str
    summary: str
    evidence: str
    created_at: float
    promoted: bool = False


class VerifiedOutcomeBridge:
    def __init__(self, recorder: Optional[Callable[..., Any]] = None):
        self.recorder = recorder
        self.records: list[OutcomeLesson] = []

    def learn(self, *, action_id: str, verification: Any, summary: str = "") -> dict[str, Any]:
        verified = bool(getattr(verification, "verified", False))
        reason = str(getattr(verification, "reason", "unknown"))
        evidence = str(getattr(verification, "evidence", "") or "")
        if not verified:
            lesson = OutcomeLesson(str(action_id), "failure_or_unverified", str(summary)[:1000], reason, time())
            self.records.append(lesson)
            return {"learned": False, "promotable": False, "reason": reason}
        lesson = OutcomeLesson(str(action_id), "verified_success", str(summary)[:1000], evidence[:1000], time())
        self.records.append(lesson)
        if self.recorder is not None:
            self.recorder(request=str(action_id), tools=[], evidence={"ok": True, "evidence": evidence}, summary=summary)
        return {"learned": True, "promotable": True, "reason": "verified_success", "record": asdict(lesson)}

    def promote(self, index: int) -> OutcomeLesson:
        if index < 0 or index >= len(self.records):
            raise IndexError("lesson_index_out_of_range")
        lesson = self.records[index]
        if lesson.outcome != "verified_success":
            raise ValueError("only_verified_success_can_be_promoted")
        promoted = OutcomeLesson(lesson.action_id, lesson.outcome, lesson.summary, lesson.evidence, lesson.created_at, True)
        self.records[index] = promoted
        return promoted
